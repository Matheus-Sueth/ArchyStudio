import sys

import pytest

from archy_studio.core import Job, Invocation, digest, has_flag, normalize_token, redact
from archy_studio.history import History

HELP = ' '.join('--' + x for x in ('file','optionsFile','authToken','authTokenIsClientCredentials','location','resultsFile','recreate','forceUnlock','debug','debugPublish'))


def job(tmp_path, operation='publish', client=False):
    p = tmp_path / 'flow with space.yaml'; p.write_text('inboundCall: {}')
    return Job(operation, p, 'sae1.pure.cloud', client, 'test-secret-token', sys.executable, digest(p))


@pytest.mark.parametrize('operation', ['create', 'publish', 'validateYaml'])
@pytest.mark.parametrize('client', [True, False])
def test_invocation(tmp_path, operation, client):
    j = job(tmp_path, operation, client); inv = Invocation(j, HELP)
    try:
        assert inv.args[:3] == [operation, '--file', str(j.path)]
        assert j.token not in str(inv.args)
        text = inv.options.read_text()
        assert f'authTokenIsClientCredentials: {str(client).lower()}' in text
        assert 'location: "sae1.pure.cloud"' in text
        for flag in ('recreate', 'forceUnlock', 'debug', 'debugPublish'):
            assert f'{flag}: false' in text
        assert '--resultsFile' in inv.args
        assert j.token not in repr(j)
        inv.results.write_text('{"authToken": "test-secret-token"}')
        assert j.token not in inv.result_text(j.token)
    finally:
        inv.close()
    assert not inv.directory.exists()


def test_missing_flag_fails_closed(tmp_path):
    with pytest.raises(ValueError, match='authTokenIsClientCredentials'):
        Invocation(job(tmp_path), HELP.replace('--authTokenIsClientCredentials', ''))


def test_changed_yaml_rejected(tmp_path):
    j = job(tmp_path); j.path.write_text('changed')
    with pytest.raises(ValueError, match='mudou'):
        Invocation(j, HELP)


def test_optional_results(tmp_path):
    inv = Invocation(job(tmp_path), HELP.replace('--resultsFile', ''))
    try:
        assert '--resultsFile' not in inv.args
    finally:
        inv.close()


def test_redaction():
    assert normalize_token(' Bearer abc123 ') == 'abc123'
    for value in ['', 'abc xyz', 'abc\nxyz']:
        with pytest.raises(ValueError): normalize_token(value)
    assert 'secret123' not in redact('token secret123', 'secret123')
    assert 'other' not in redact('clientSecret: other', '')
    assert not has_flag('--fileName', 'file')
    assert has_flag('--file <path>', 'file')


def test_history_no_secrets(tmp_path):
    j = job(tmp_path); db = tmp_path / 'db.sqlite'; h = History(db)
    h.start(j); h.finish(j.id, 'Concluído (exit 0)', 0)
    assert h.recent()[0][-1] == 0
    h.close()
    assert j.token.encode() not in db.read_bytes()
    assert str(j.path).encode() not in db.read_bytes()


def test_history_restart(tmp_path):
    j = job(tmp_path); db = tmp_path / 'db.sqlite'; h = History(db)
    h.start(j); h.close(); h = History(db)
    assert 'desconhecido' in h.recent()[0][-2]; h.close()
