"""Integração local com CLI simulada: nenhum acesso a Genesys."""
import sys
import time

import pytest

pytest.importorskip('PySide6')
from PySide6.QtCore import QCoreApplication  # noqa: E402
from archy_studio.core import Job, digest
from archy_studio.history import History
from archy_studio.runner import Runner


def spin(app, condition):
    deadline = time.monotonic() + 8
    while not condition() and time.monotonic() < deadline:
        app.processEvents(); time.sleep(0.01)
    assert condition()


def test_queue_with_mock_cli(tmp_path, monkeypatch):
    app = QCoreApplication.instance() or QCoreApplication([])
    p = tmp_path / 'flow.yaml'; p.write_text('inboundCall: {}')
    cli = tmp_path / 'fake.py'
    cli.write_text('''import sys, pathlib, json
args = sys.argv[1:]
if '--help' in args:
    print('--file --optionsFile --authToken --authTokenIsClientCredentials --location --resultsFile --debug --recreate --forceUnlock')
    sys.exit(0)
opt = pathlib.Path(args[args.index('--optionsFile')+1]).read_text()
token = json.loads(opt.splitlines()[0].split(': ', 1)[1])
print('credential ' + token, flush=True)
pathlib.Path(args[args.index('--resultsFile')+1]).write_text(json.dumps({'ok': True}))
sys.exit(5 if args[0] == 'create' else 0)
''')
    h = History(tmp_path / 'history.db'); runner = Runner(h)
    # QProcess invokes the real Python interpreter with a fake CLI script prepended.
    original_start = runner.process.start
    monkeypatch.setattr(runner.process, 'start', lambda program, args: original_start(program, [str(cli), *args]))
    states = {}; logs = []
    runner.state.connect(lambda id, state: states.update({id: state}))
    runner.log.connect(lambda id, text: logs.append(text))
    def make(op): return Job(op, p, 'sae1.pure.cloud', False, 'fake-secret-123', sys.executable, digest(p))
    a, b, c = make('validateYaml'), make('create'), make('publish')
    for j in (a,b,c): runner.enqueue(j)
    spin(app, lambda: runner.paused and runner.active is None)
    assert states[a.id].startswith('Concluído') and states[b.id].startswith('Falha')
    assert states[c.id] == 'Na fila' and len(runner.pending) == 1
    runner.resume(); spin(app, lambda: states[c.id].startswith('Concluído'))
    assert 'fake-secret-123' not in '\n'.join(logs)
    assert len(h.recent()) == 3
    h.close()
