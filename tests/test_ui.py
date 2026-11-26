"""Regressão da interface: Qt offscreen, sem operações no Genesys."""
import os
import subprocess
import sys
import textwrap

import pytest


def test_readable_form_and_native_controls(tmp_path):
    pytest.importorskip('PySide6')
    # Processo separado: o teste do Runner usa QCoreApplication.
    script = textwrap.dedent("""
        import sys
        from pathlib import Path
        from PySide6.QtCore import QSettings, Qt
        from PySide6.QtGui import QPalette
        from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QScrollArea
        from archy_studio.ui import MainWindow, apply_theme

        folder = Path(sys.argv[1])
        app = QApplication([])
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        for scope in (QSettings.Scope.UserScope, QSettings.Scope.SystemScope):
            QSettings.setPath(QSettings.Format.IniFormat, scope, str(folder))
        MainWindow._detect = lambda self: None
        apply_theme(app)
        window = MainWindow(folder)
        window.resize(1280, 820)
        window.show()
        app.processEvents()

        fields = (window.program, window.region, window.kind, window.token, window.file)
        names = ('Executável Archy', 'Região Genesys Cloud', 'Tipo de token',
                 'Access token', 'Arquivo do fluxo')
        for field, name in zip(fields, names):
            assert field.minimumHeight() >= 42
            assert field.height() >= 42
            assert field.accessibleName() == name
            assert any(label.buddy() == field and label.text() == name
                       for label in window.findChildren(QLabel))
        assert window.token.echoMode() == QLineEdit.EchoMode.Password
        assert window.kind.count() == 2
        assert window.kind.itemData(0) is False
        assert window.kind.itemData(1) is True
        assert window.region.findData('sae1.pure.cloud') >= 0

        palette = app.palette()
        def luminance(color):
            channels = [color.redF(), color.greenF(), color.blueF()]
            linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4
                      for c in channels]
            return sum(a*b for a,b in zip(linear, (.2126, .7152, .0722)))
        bg = luminance(palette.color(QPalette.ColorRole.Base))
        for role in (QPalette.ColorRole.Text, QPalette.ColorRole.PlaceholderText):
            fg = luminance(palette.color(role))
            assert (max(fg,bg)+.05)/(min(fg,bg)+.05) >= 4.5

        scroll = window.findChild(QScrollArea, 'configurationScroll')
        assert scroll is not None and scroll.widgetResizable()
        assert scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        window.resize(900, 600)
        app.processEvents()
        scroll.ensureWidgetVisible(window.file)
        app.processEvents()
        assert window.file.width() >= 100
        assert scroll.widget().width() <= scroll.viewport().width()
        calls = []
        window._enqueue = calls.append
        for operation in ('validateYaml', 'create', 'publish'):
            button = window.operation_buttons[operation]
            assert button.minimumHeight() >= 44
            button.click()
        assert calls == ['validateYaml', 'create', 'publish']
        window.close()
    """)
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
