from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from PySide6.QtCore import QLockFile, QProcess, QSettings, QStandardPaths, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QPalette, QTextCursor
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSizePolicy, QSplitter, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .core import Job, OPERATIONS, REGIONS, executable
from .history import History
from .runner import Runner

STYLE = '''
/* Define os estados explicitamente; não depende do tema claro/escuro do Windows. */
QWidget { color: #e5edf7; font-size: 14px; }
QMainWindow, QWidget#workspace { background: #0f1724; }
QLabel { background: transparent; }
QLabel#brand { font-size: 27px; font-weight: 700; color: #f8fafc; }
QLabel#muted { color: #b4c1d4; font-size: 12px; }
QLabel#sectionTitle { color: #f1f5f9; font-size: 17px; font-weight: 700; }
QLabel#fieldLabel { color: #e2e8f0; font-size: 14px; font-weight: 600; }
QLabel#sectionCaption { color: #a9bad1; font-size: 12px; }
QLabel#operationWarning { color: #fcd48a; font-size: 12px; padding: 8px; background: #2c241a; border-radius: 6px; }
QFrame#panel { background: #182333; border: 1px solid #34445a; border-radius: 10px; }
QLineEdit, QComboBox {
    background-color: #0d1624; color: #f8fafc; border: 1px solid #62748d;
    border-radius: 6px; padding: 8px 11px; font-size: 14px;
    selection-background-color: #3156a5; selection-color: #ffffff;
}
QLineEdit:hover, QComboBox:hover { border-color: #93a9c4; }
QLineEdit:focus, QComboBox:focus { border: 2px solid #85aaff; padding: 7px 10px; }
QLineEdit:disabled, QComboBox:disabled { background-color: #243044; color: #a3b2c7; border-color: #425168; }
QComboBox { padding-right: 36px; }
QComboBox:focus { padding-right: 35px; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right;
    width: 30px; border-left: 1px solid #62748d; background: #26364e;
    border-top-right-radius: 5px; border-bottom-right-radius: 5px; }
QComboBox QAbstractItemView { background-color: #1e2b40; color: #f8fafc;
    border: 1px solid #7085a3; padding: 4px; outline: 0;
    selection-background-color: #3156a5; selection-color: #ffffff; }
QComboBox QAbstractItemView::item { padding: 8px 10px; min-height: 22px; }
QPushButton { background-color: #29394f; color: #f1f5f9; border: 1px solid #536783;
    border-radius: 6px; padding: 8px 12px; font-weight: 600; }
QPushButton:hover { background-color: #384c68; border-color: #8098b9; }
QPushButton:focus { border: 2px solid #85aaff; padding: 7px 11px; }
QPushButton:pressed { background-color: #1b2a40; }
QPushButton:disabled { color: #a0aec0; background-color: #202b3a; border-color: #364359; }
QPushButton#primary { background-color: #3156a5; border-color: #688bea; color: #ffffff; }
QPushButton#primary:hover { background-color: #3d65b8; }
QPushButton#primary:focus { border-color: #bed1ff; }
QPlainTextEdit, QTableWidget { background-color: #0d1624; color: #e5edf7; border: 1px solid #455771;
    border-radius: 6px; gridline-color: #334155; selection-background-color: #3156a5;
    selection-color: #ffffff; alternate-background-color: #142033; }
QPlainTextEdit { padding: 8px; }
QHeaderView::section { background-color: #26364d; color: #dbe7f7; padding: 9px 6px; border: none; border-bottom: 1px solid #536783; font-weight: 600; }
QTabBar::tab { padding: 11px 24px; background-color: #202d40; color: #bdcce0; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { background-color: #2a3c57; color: #ffffff; border-bottom: 2px solid #85aaff; }
QTabBar::tab:focus { color: #ffffff; }
QTabWidget::pane { border: 1px solid #34445a; }
QSplitter::handle { background-color: #34445a; }
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: #142033; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: #62748d; min-height: 28px; border-radius: 5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QToolTip { background-color: #26364e; color: #ffffff; border: 1px solid #93a9c4; padding: 5px; }
'''


def apply_theme(app):
    app.setStyle('Fusion')
    palette = QPalette()
    colors = {
        'Window': '#0f1724', 'WindowText': '#e5edf7', 'Base': '#0d1624',
        'AlternateBase': '#142033', 'Text': '#f8fafc', 'Button': '#29394f',
        'ButtonText': '#f1f5f9', 'PlaceholderText': '#a9bad1',
        'Highlight': '#3156a5', 'HighlightedText': '#ffffff',
        'ToolTipBase': '#26364e', 'ToolTipText': '#ffffff',
    }
    for name, value in colors.items():
        palette.setColor(getattr(QPalette.ColorRole, name), QColor(value))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)


def heading(text, name='sectionTitle'):
    w = label(text)
    w.setObjectName(name)
    return w


def field(layout, title, widget, control=None, hint=None):
    caption = heading(title, 'fieldLabel')
    target = control if control is not None else widget
    caption.setBuddy(target)
    target.setAccessibleName(title)
    target.setMinimumHeight(42)
    target.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    layout.addWidget(caption)
    if control is None:
        layout.addWidget(widget)
    else:
        layout.addLayout(widget)
    if hint:
        note = heading(hint, 'sectionCaption')
        note.setWordWrap(True)
        layout.addWidget(note)
        target.setAccessibleDescription(hint)


def field_row(control, *buttons):
    row = QHBoxLayout()
    row.setSpacing(7)
    row.addWidget(control, 1)
    for action in buttons:
        row.addWidget(action)
    return row



def button(text, callback, primary=False):
    b = QPushButton(text)
    if primary:
        b.setObjectName('primary')
    b.setMinimumHeight(38)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
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
    l.setContentsMargins(16, 16, 16, 16)
    l.setSpacing(9)
    return w, l


def table(headers):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    t.setAlternatingRowColors(True)
    t.verticalHeader().setDefaultSectionSize(34)
    t.verticalHeader().hide()
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    return t


class MainWindow(QMainWindow):
    def __init__(self, data_dir):
        super().__init__()
        self.setWindowTitle('Sueth Archy Studio | 0.1.0')
        self.resize(1280, 820)
        self.setMinimumSize(900, 600)
        self.settings = QSettings('Sueth', 'ArchyStudio')
        self.history = History(data_dir / 'history.sqlite3')
        self.runner = Runner(self.history, self)
        self.rows = {}
        self.logs = defaultdict(str)
        self.runner.log.connect(self._log)
        self.runner.state.connect(self._state)
        self.runner.changed.connect(self._changed)
        root = QWidget()
        root.setObjectName('workspace')
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        top = QHBoxLayout()
        brand = label('Sueth Archy Studio')
        brand.setObjectName('brand')
        top.addWidget(brand)
        top.addStretch()
        self.version = label('Archy: não verificado', True)
        self.version.setWordWrap(True)
        self.version.setMaximumWidth(360)
        top.addWidget(self.version)
        layout.addLayout(top)
        layout.addWidget(label('ARCHITECT  /  WORKSPACE LOCAL  /  v0.1.0', True))
        tabs = QTabWidget()
        layout.addWidget(tabs, 1)
        work = QWidget()
        tabs.addTab(work, 'Executar')
        wl = QHBoxLayout(work)
        wl.setContentsMargins(12, 12, 12, 12)
        workspace = QSplitter(Qt.Orientation.Horizontal)
        workspace.setChildrenCollapsible(False)
        workspace.setHandleWidth(8)
        wl.addWidget(workspace)
        # A configuração tem largura própria e rolagem, sem disputar altura com os logs.
        scroll = QScrollArea()
        scroll.setObjectName('configurationScroll')
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(390)
        config, cl = panel()
        scroll.setWidget(config)
        workspace.addWidget(scroll)
        cl.addWidget(heading('01  Configuração'))
        desc = heading('Escolha o executável e a organização de destino.', 'sectionCaption')
        desc.setWordWrap(True)
        cl.addWidget(desc)
        self.program = QLineEdit(self.settings.value('program', '', type=str))
        self.program.setPlaceholderText('Archy no PATH ou caminho do archy.exe')
        self.program.setMinimumWidth(100)
        locate = button('Localizar', self._browse_program)
        verify = button('Verificar', self._detect)
        field(cl, 'Executável Archy', field_row(self.program, locate, verify), self.program)
        self.region = QComboBox()
        self.region.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.region.setMinimumContentsLength(16)
        for title, domain in REGIONS.items():
            self.region.addItem(f'{title} — {domain}', domain)
        saved = self.region.findData(self.settings.value('region', REGIONS['São Paulo']))
        self.region.setCurrentIndex(max(saved, 0))
        field(cl, 'Região Genesys Cloud', self.region)
        self.kind = QComboBox()
        self.kind.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.kind.setMinimumContentsLength(16)
        self.kind.addItem('User Token (PKCE / Authorization Code)', False)
        self.kind.addItem('Client Credentials Token', True)
        field(cl, 'Tipo de token', self.kind)
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText('Cole o access token aqui')
        self.token.setMinimumWidth(100)
        clear = button('Limpar', self.token.clear)
        field(cl, 'Access token', field_row(self.token, clear), self.token,
              'O token fica oculto e não é salvo no histórico.')
        cl.addSpacing(12)
        cl.addWidget(heading('02  Fluxo YAML'))
        self.file = QLineEdit()
        self.file.setPlaceholderText('Selecione um arquivo .yaml ou .yml')
        self.file.setMinimumWidth(100)
        select = button('Selecionar', self._browse_yaml)
        field(cl, 'Arquivo do fluxo', field_row(self.file, select), self.file)
        cl.addSpacing(12)
        cl.addWidget(heading('03  Operação'))
        self.operation_buttons = {}
        actions = QHBoxLayout()
        actions.setSpacing(7)
        cl.addLayout(actions)
        for op, text in OPERATIONS.items():
            action = button(text, lambda checked=False, op=op: self._enqueue(op), op == 'publish')
            action.setAccessibleName(text)
            action.setMinimumHeight(44)
            if op == 'publish':
                cl.addWidget(action)
            else:
                actions.addWidget(action)
            self.operation_buttons[op] = action
        self.notice = heading('CREATE e PUBLISH alteram a organização de destino.', 'operationWarning')
        self.notice.setWordWrap(True)
        cl.addWidget(self.notice)
        cl.addStretch(1)
        # Preserve the form's minimum width including the native scrollbar.
        # Font metrics and scrollbars differ between Windows and Linux.
        config.ensurePolished()
        cl.activate()
        scroll.ensurePolished()
        scroll.setMinimumWidth(max(
            390, config.minimumSizeHint().width()
            + scroll.verticalScrollBar().sizeHint().width()
            + 2 * scroll.frameWidth() + 4,
        ))
        QWidget.setTabOrder(self.program, locate)
        QWidget.setTabOrder(locate, verify)
        QWidget.setTabOrder(verify, self.region)
        QWidget.setTabOrder(self.region, self.kind)
        QWidget.setTabOrder(self.kind, self.token)
        QWidget.setTabOrder(self.token, clear)
        QWidget.setTabOrder(clear, self.file)
        QWidget.setTabOrder(self.file, select)
        QWidget.setTabOrder(select, self.operation_buttons['validateYaml'])
        QWidget.setTabOrder(self.operation_buttons['validateYaml'], self.operation_buttons['create'])
        QWidget.setTabOrder(self.operation_buttons['create'], self.operation_buttons['publish'])
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)
        workspace.addWidget(splitter)
        workspace.setStretchFactor(0, 0)
        workspace.setStretchFactor(1, 1)
        workspace.setSizes([450, 750])
        queue, ql = panel(); splitter.addWidget(queue)
        qtop = QHBoxLayout(); qtop.addWidget(heading('Fila de operações')); qtop.addStretch()
        self.queue_status = label('Pronta', True); qtop.addWidget(self.queue_status)
        self.resume = button('Continuar fila', self.runner.resume); qtop.addWidget(self.resume)
        qtop.addWidget(button('Remover pendente', self._remove)); ql.addLayout(qtop)
        self.jobs = table(['Operação', 'Arquivo', 'Região', 'Status']); ql.addWidget(self.jobs)
        self.jobs.itemSelectionChanged.connect(self._show_log)
        console, ol = panel(); splitter.addWidget(console)
        ctop = QHBoxLayout(); ctop.addWidget(heading('Console')); ctop.addStretch(); ctop.addWidget(button('Copiar', self._copy)); ctop.addWidget(button('Salvar TXT', self._save)); ol.addLayout(ctop)
        ol.addWidget(label('Selecione uma execução para acompanhar os logs.', True))
        self.output = QPlainTextEdit(); self.output.setReadOnly(True); self.output.setFont(QFont('Consolas', 11)); ol.addWidget(self.output)
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
    app = QApplication([]); app.setApplicationName('Sueth Archy Studio'); app.setOrganizationName('Sueth'); apply_theme(app)
    path = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)); path.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(path / 'studio.lock'))
    if not lock.tryLock(0):
        QMessageBox.warning(None, 'Sueth Archy Studio', 'Outra instância está aberta. Utilize uma instância por vez.'); return 1
    window = MainWindow(path); window.show()
    try: return app.exec()
    finally: lock.unlock()
