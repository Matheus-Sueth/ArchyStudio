from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from PySide6.QtCore import QLockFile, QProcess, QSettings, QStandardPaths, QTimer, Qt
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QSplitter, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .core import Job, OPERATIONS, REGIONS, executable
from .history import History
from .runner import Runner

STYLE = '''
QWidget { background: #151922; color: #e6eaf2; font-size: 13px; }
QMainWindow { background: #11151d; }
QLabel#brand { font-size: 25px; font-weight: 700; color: #f4f6fa; }
QLabel#muted { color: #a1aec3; }
QFrame#panel { background: #1b2130; border: 1px solid #343e52; border-radius: 8px; }
QFrame#panel QLabel { background: transparent; }
QPushButton, QLineEdit, QComboBox { background: #222b3b; border: 1px solid #3d4961; border-radius: 5px; padding: 8px; }
QPushButton:hover { background: #34415b; } QPushButton:disabled { color: #727e92; background: #1d2430; }
QPushButton#primary { background: #5145c4; color: white; font-weight: 600; }
QPushButton#primary:hover { background: #675be0; }
QPlainTextEdit, QTableWidget { background: #10151d; border: 1px solid #343e52; border-radius: 5px; gridline-color: #30394a; }
QHeaderView::section { background: #262f40; color: #c6d0e1; padding: 7px; border: none; }
QTabBar::tab { padding: 10px 18px; background: #202838; } QTabBar::tab:selected { background: #403798; }
QTabWidget::pane { border: 1px solid #343e52; }
QSplitter::handle { background: #343e52; }
'''


def button(text, callback, primary=False):
    b = QPushButton(text)
    if primary:
        b.setObjectName('primary')
    b.clicked.connect(callback)
    return b


def label(text, muted=False):
    w = QLabel(text)
    w.setTextFormat(Qt.TextFormat.PlainText)
    if muted:
        w.setObjectName('muted')
    return w


def panel():
    w = QFrame()
    w.setObjectName('panel')
    l = QVBoxLayout(w)
    l.setContentsMargins(14, 14, 14, 14)
    return w, l


def table(headers):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    t.verticalHeader().hide()
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    return t


class MainWindow(QMainWindow):
    def __init__(self, data_dir):
        super().__init__()
        self.setWindowTitle('Sueth Archy Studio | 0.1.0')
        self.resize(1100, 760)
        self.setMinimumSize(760, 590)
        self.settings = QSettings('Sueth', 'ArchyStudio')
        self.history = History(data_dir / 'history.sqlite3')
        self.runner = Runner(self.history, self)
        self.rows = {}
        self.logs = defaultdict(str)
        self.runner.log.connect(self._log)
        self.runner.state.connect(self._state)
        self.runner.changed.connect(self._changed)
        root = QWidget(); self.setCentralWidget(root)
        layout = QVBoxLayout(root); layout.setContentsMargins(20, 16, 20, 16)
        top = QHBoxLayout()
        brand = label('Sueth Archy Studio'); brand.setObjectName('brand'); top.addWidget(brand)
        top.addStretch(); self.version = label('Archy: não verificado', True); top.addWidget(self.version)
        layout.addLayout(top)
        layout.addWidget(label('ARCHITECT  /  FERRAMENTA LOCAL  /  v0.1.0', True))
        tabs = QTabWidget(); layout.addWidget(tabs, 1)
        work = QWidget(); tabs.addTab(work, 'Executar'); wl = QVBoxLayout(work)
        config, cl = panel(); wl.addWidget(config)
        form = QFormLayout(); cl.addLayout(form)
        self.program = QLineEdit(self.settings.value('program', '', type=str)); self.program.setPlaceholderText('Detectar pelo PATH ou selecionar archy.exe')
        pl = QHBoxLayout(); pl.addWidget(self.program, 1); pl.addWidget(button('Localizar', self._browse_program)); pl.addWidget(button('Verificar', self._detect)); form.addRow('Archy', pl)
        self.region = QComboBox()
        for title, domain in REGIONS.items(): self.region.addItem(f'{title} — {domain}', domain)
        saved = self.region.findData(self.settings.value('region', REGIONS['São Paulo']))
        self.region.setCurrentIndex(max(saved, 0)); form.addRow('Região', self.region)
        self.kind = QComboBox(); self.kind.addItem('User Token (PKCE / Authorization Code)', False); self.kind.addItem('Client Credentials Token', True); form.addRow('Tipo de token', self.kind)
        self.token = QLineEdit(); self.token.setEchoMode(QLineEdit.EchoMode.Password); self.token.setPlaceholderText('Access token da sessão — não é salvo')
        tl = QHBoxLayout(); tl.addWidget(self.token, 1); tl.addWidget(button('Limpar', self.token.clear)); form.addRow('Access token', tl)
        self.file = QLineEdit(); self.file.setPlaceholderText('Caminho do arquivo .yaml ou .yml')
        fl = QHBoxLayout(); fl.addWidget(self.file, 1); fl.addWidget(button('Selecionar YAML', self._browse_yaml)); form.addRow('Fluxo YAML', fl)
        actions = QHBoxLayout(); cl.addLayout(actions)
        for op, text in OPERATIONS.items(): actions.addWidget(button(text, lambda checked=False, op=op: self._enqueue(op), op == 'publish'))
        self.notice = label('Uma execução por vez. CREATE e PUBLISH alteram a organização de destino.', True); cl.addWidget(self.notice)
        splitter = QSplitter(Qt.Orientation.Vertical); wl.addWidget(splitter, 1)
        queue, ql = panel(); splitter.addWidget(queue)
        qtop = QHBoxLayout(); qtop.addWidget(label('Fila de operações')); qtop.addStretch()
        self.queue_status = label('Pronta', True); qtop.addWidget(self.queue_status)
        self.resume = button('Continuar fila', self.runner.resume); qtop.addWidget(self.resume)
        qtop.addWidget(button('Remover pendente', self._remove)); ql.addLayout(qtop)
        self.jobs = table(['Operação', 'Arquivo', 'Região', 'Status']); ql.addWidget(self.jobs)
        self.jobs.itemSelectionChanged.connect(self._show_log)
        console, ol = panel(); splitter.addWidget(console)
        ctop = QHBoxLayout(); ctop.addWidget(label('Console da operação selecionada')); ctop.addStretch(); ctop.addWidget(button('Copiar', self._copy)); ctop.addWidget(button('Salvar TXT', self._save)); ol.addLayout(ctop)
        self.output = QPlainTextEdit(); self.output.setReadOnly(True); self.output.setFont(QFont('Consolas', 10)); ol.addWidget(self.output)
        splitter.setSizes([150, 235])
        ht = QWidget(); tabs.addTab(ht, 'Histórico'); hl = QVBoxLayout(ht)
        hl.addWidget(label('Metadados locais das últimas 200 execuções. Não inclui tokens nem logs.', True)); hl.addWidget(button('Atualizar', self._refresh_history))
        self.history_table = table(['Início (UTC)', 'Operação', 'Arquivo', 'Região', 'Status', 'Exit']); hl.addWidget(self.history_table)
        self.probe = QProcess(self); self.probe.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.probe.finished.connect(self._detected); self.probe.errorOccurred.connect(self._probe_error)
        self.probe_timer = QTimer(self); self.probe_timer.setSingleShot(True); self.probe_timer.timeout.connect(self.probe.kill)
        self._refresh_history(); self._changed(); QTimer.singleShot(0, self._detect)

    def _browse_program(self):
        p, _ = QFileDialog.getOpenFileName(self, 'Selecionar Archy', '', 'Executáveis (*)')
        if p: self.program.setText(p); self._detect()

    def _browse_yaml(self):
        p, _ = QFileDialog.getOpenFileName(self, 'Selecionar fluxo', self.settings.value('last_dir', '', type=str), 'YAML (*.yaml *.yml)')
        if p: self.file.setText(p); self.settings.setValue('last_dir', str(Path(p).parent))

    def _detect(self):
        if self.probe.state() != QProcess.ProcessState.NotRunning or self.runner.active: return
        try: path = executable(self.program.text())
        except ValueError as exc: self.version.setText(str(exc)); return
        self.version.setText('Archy: verificando…'); self.probe_timer.start(15_000); self.probe.start(path, ['--version']); self.probe.closeWriteChannel()

    def _detected(self, code, status):
        self.probe_timer.stop()
        output = bytes(self.probe.readAllStandardOutput()).decode('utf-8', 'replace')
        versions = re.findall(r'(?m)^\s*v?(\d+\.\d+\.\d+)\s*$', output)
        self.version.setText(f'Archy {versions[-1]}' if code == 0 and versions else ('Archy localizado (versão não identificada)' if code == 0 else 'Falha ao verificar Archy'))

    def _probe_error(self, error):
        self.probe_timer.stop(); self.version.setText('Falha ao executar Archy')

    def _enqueue(self, op):
        if self.probe.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.information(self, 'Archy', 'Aguarde a verificação do executável terminar.'); return
        try:
            job = Job.build(op, self.file.text().strip().strip('"'), self.region.currentData(), self.kind.currentData(), self.token.text(), self.program.text())
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Dados incompletos', str(exc)); return
        if op != 'validateYaml':
            answer = QMessageBox.question(self, 'Confirmar operação no Genesys Cloud', f'{OPERATIONS[op]}\n\nArquivo: {job.path}\nRegião: {job.region}\n\nA organização é determinada pelo token informado, não apenas pela região. Confirme que é a organização correta. A operação pode modificar recursos remotos.', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes: return
        self.settings.setValue('program', self.program.text()); self.settings.setValue('region', job.region)
        r = self.jobs.rowCount(); self.jobs.insertRow(r); self.rows[job.id] = r
        for i, value in enumerate([OPERATIONS[op], job.path.name, job.region, 'Na fila']):
            item = QTableWidgetItem(value); item.setData(Qt.ItemDataRole.UserRole, job.id); self.jobs.setItem(r, i, item)
        self.jobs.selectRow(r); self.runner.enqueue(job)

    def _selected(self):
        items = self.jobs.selectedItems(); return items[0].data(Qt.ItemDataRole.UserRole) if items else None

    def _remove(self):
        job_id = self._selected()
        if job_id: self.runner.remove(job_id)

    def _state(self, job_id, status):
        if job_id in self.rows: self.jobs.item(self.rows[job_id], 3).setText(status)
        self._refresh_history()

    def _changed(self):
        self.resume.setEnabled(self.runner.paused)
        state = 'Pausada após falha' if self.runner.paused else ('Em execução' if self.runner.active else 'Pronta')
        self.queue_status.setText(f'{state} | {len(self.runner.pending)} pendente(s)')

    def _log(self, job_id, text):
        self.logs[job_id] = (self.logs[job_id] + text + '\n')[-500_000:]
        if self._selected() == job_id: self._show_log()

    def _show_log(self):
        self.output.setPlainText(self.logs.get(self._selected(), '')); self.output.moveCursor(QTextCursor.MoveOperation.End)

    def _copy(self):
        QApplication.clipboard().setText(self.output.toPlainText())

    def _save(self):
        if not self.output.toPlainText(): return
        p, _ = QFileDialog.getSaveFileName(self, 'Salvar console', 'archy-console.txt', 'Texto (*.txt)')
        if p:
            try: Path(p).write_text(self.output.toPlainText(), encoding='utf-8')
            except OSError as exc: QMessageBox.warning(self, 'Falha ao salvar', str(exc))

    def _refresh_history(self):
        if not hasattr(self, 'history_table'): return
        rows = self.history.recent(); self.history_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, val in enumerate(row): self.history_table.setItem(i, j, QTableWidgetItem('' if val is None else str(val)))

    def closeEvent(self, event):
        if self.runner.active:
            QMessageBox.information(self, 'Operação em andamento', 'Aguarde o término do Archy. Encerrar o aplicativo não desfaz operações remotas.'); event.ignore(); return
        if self.runner.pending and QMessageBox.question(self, 'Fechar', 'Descartar as operações pendentes?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            event.ignore(); return
        self.runner.clear(); self.token.clear(); self.history.close(); event.accept()


def main():
    app = QApplication([]); app.setApplicationName('Sueth Archy Studio'); app.setOrganizationName('Sueth'); app.setStyle('Fusion'); app.setStyleSheet(STYLE)
    path = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)); path.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(path / 'studio.lock'))
    if not lock.tryLock(0):
        QMessageBox.warning(None, 'Sueth Archy Studio', 'Outra instância está aberta. Utilize uma instância por vez.'); return 1
    window = MainWindow(path); window.show()
    try: return app.exec()
    finally: lock.unlock()
