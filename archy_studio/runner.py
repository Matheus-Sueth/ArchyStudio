from __future__ import annotations

import codecs
from collections import deque

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from .core import Invocation, Job, redact
from .history import History


class Runner(QObject):
    log = Signal(str, str)
    state = Signal(str, str)
    changed = Signal()

    def __init__(self, history: History, parent=None):
        super().__init__(parent)
        self.history = history
        self.pending: deque[Job] = deque()
        self.active: Job | None = None
        self.paused = False
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._help_timeout)
        self.phase = ''
        self.invocation: Invocation | None = None
        self.buffer = ''
        self.discard_line = False
        self.help_text = ''
        self.decoder = codecs.getincrementaldecoder('utf-8')('replace')

    def enqueue(self, job: Job):
        self.pending.append(job)
        self.state.emit(job.id, 'Na fila')
        self.changed.emit()
        self._next()

    def remove(self, job_id: str):
        for job in self.pending:
            if job.id == job_id:
                self.pending.remove(job)
                self.state.emit(job_id, 'Removido')
                self.changed.emit()
                return

    def clear(self):
        for job in list(self.pending):
            self.remove(job.id)

    def resume(self):
        self.paused = False
        self.changed.emit()
        self._next()

    def _next(self):
        if self.active or self.paused or not self.pending:
            return
        self.active = self.pending.popleft()
        job = self.active
        self.changed.emit()
        try:
            self.history.start(job)
            job.check_file()
        except Exception as exc:
            self._complete('Falha local', None, str(exc))
            return
        self.state.emit(job.id, 'Verificando CLI')
        self.phase = 'help'
        self.help_text = ''
        self._reset_decoder()
        self.process.setWorkingDirectory(str(job.path.parent))
        self.timer.start(20_000)
        self.process.start(job.program, [job.operation, '--help'])
        self.process.closeWriteChannel()

    def _reset_decoder(self):
        self.decoder = codecs.getincrementaldecoder('utf-8')('replace')
        self.buffer = ''
        self.discard_line = False

    def _read(self, final=False):
        data = bytes(self.process.readAllStandardOutput())
        text = self.decoder.decode(data, final=final)
        if self.phase == 'help':
            self.help_text += text
            if len(self.help_text) > 500_000:
                self.help_text = self.help_text[:500_000]
            return
        if not self.active:
            return
        if self.discard_line:
            _, sep, text = text.partition('\n')
            if not sep:
                return
            self.discard_line = False
        self.buffer += text
        # Só emite linhas completas, evitando vazar tokens quebrados em chunks.
        lines = self.buffer.split('\n')
        self.buffer = lines.pop()
        for line in lines:
            self.log.emit(self.active.id, redact(line.rstrip('\r'), self.active.token) if len(line) <= 512_000 else '[Linha excessivamente longa omitida]')
        if len(self.buffer) > 512_000:
            self.log.emit(self.active.id, '[Linha excessivamente longa omitida]')
            self.buffer = ''
            self.discard_line = True
        if final and self.buffer:
            self.log.emit(self.active.id, redact(self.buffer, self.active.token))
            self.buffer = ''

    def _finished(self, code, exit_status):
        if not self.active:
            return
        self.timer.stop()
        self._read(final=True)
        job = self.active
        normal = exit_status == QProcess.ExitStatus.NormalExit
        if self.phase == 'help':
            if code != 0 or not normal:
                self._complete('Falha local', code, 'Não foi possível consultar --help. Nenhuma operação iniciada.')
                return
            try:
                self.invocation = Invocation(job, self.help_text)
            except Exception as exc:
                self._complete('Falha local', None, str(exc))
                return
            self.phase = 'run'
            self._reset_decoder()
            self.state.emit(job.id, 'Executando')
            self.log.emit(job.id, f'[Studio] {job.operation} | {job.region} | {job.path.name}')
            self.process.start(job.program, self.invocation.args)
            self.process.closeWriteChannel()
            return
        if self.invocation:
            try:
                result = self.invocation.result_text(job.token)
                if result:
                    self.log.emit(job.id, '\n[Resultado Archy]\n' + result)
            except OSError:
                self.log.emit(job.id, '[Studio] Não foi possível ler o resultado JSON.')
        status = 'Concluído (exit 0)' if normal and code == 0 else (
            'Falha Archy / conferir destino' if normal else 'Estado remoto desconhecido')
        self._complete(status, code if normal else None, f'Archy encerrou (exit={code}).')

    def _help_timeout(self):
        if self.phase == 'help' and self.active:
            self.process.kill()

    def _error(self, error):
        if self.active and error == QProcess.ProcessError.FailedToStart:
            self._complete('Falha local', None, 'Não foi possível iniciar o executável do Archy.')

    def _complete(self, status, code, message):
        if not self.active:
            return
        self.timer.stop()
        job = self.active
        self.log.emit(job.id, redact('[Studio] ' + message, job.token))
        if self.invocation:
            try:
                self.invocation.close()
            except OSError:
                self.log.emit(job.id, '[ATENÇÃO] Falha ao limpar opções temporárias; revogue o token e verifique a pasta temporária.')
            self.invocation = None
        try:
            self.history.finish(job.id, status, code)
        except Exception:
            self.log.emit(job.id, '[Studio] Falha ao registrar histórico local.')
        self.active = None
        self.phase = ''
        self.help_text = ''
        self.buffer = ''
        if not status.startswith('Concluído'):
            self.paused = True
        self.state.emit(job.id, status)
        self.changed.emit()
        QTimer.singleShot(0, self._next)
