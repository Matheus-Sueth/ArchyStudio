"""Contratos locais. O Archy continua responsável pelas regras do Architect."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

REGIONS = {
    'São Paulo': 'sae1.pure.cloud', 'Virgínia': 'mypurecloud.com',
    'Oregon': 'usw2.pure.cloud', 'Irlanda': 'mypurecloud.ie',
    'Frankfurt': 'mypurecloud.de', 'Londres': 'euw2.pure.cloud',
    'Canadá': 'cac1.pure.cloud', 'Sydney': 'mypurecloud.com.au',
    'Tóquio': 'mypurecloud.jp', 'Mumbai': 'aps1.pure.cloud',
}
OPERATIONS = {'validateYaml': 'Validar YAML', 'create': 'Criar fluxo', 'publish': 'Publicar fluxo'}
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')


def normalize_token(value: str) -> str:
    value = re.sub(r'^Bearer\s+', '', value.strip(), flags=re.I)
    if not value or any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError('Informe um access token válido, sem espaços internos.')
    return value


def executable(value: str = '') -> str:
    candidate = value.strip().strip('"')
    path = shutil.which(candidate or 'archy')
    if not path and candidate and Path(candidate).is_file():
        path = candidate
    if not path:
        raise ValueError('Archy não encontrado. Selecione o executável instalado.')
    path = str(Path(path).resolve())
    if os.name == 'nt' and Path(path).suffix.lower() != '.exe':
        raise ValueError('Nesta versão, selecione o archy.exe nativo (launchers .cmd/.bat não suportados).')
    if not os.access(path, os.X_OK):
        raise ValueError('O arquivo selecionado não é executável.')
    return path


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


@dataclass(frozen=True)
class Job:
    operation: str
    path: Path
    region: str
    client_credentials: bool
    token: str = field(repr=False, compare=False)
    program: str = ''
    sha256: str = ''
    id: str = field(default_factory=lambda: uuid4().hex)

    @classmethod
    def build(cls, operation: str, path: str, region: str, client_credentials: bool,
              token: str, program: str) -> Job:
        if operation not in OPERATIONS or region not in REGIONS.values():
            raise ValueError('Operação ou região não suportada.')
        p = Path(path).expanduser().resolve(strict=True)
        if not p.is_file() or p.suffix.lower() not in {'.yaml', '.yml'}:
            raise ValueError('Selecione um arquivo .yaml ou .yml.')
        return cls(operation, p, region, client_credentials, normalize_token(token),
                   executable(program), digest(p))

    def check_file(self) -> None:
        if digest(self.path) != self.sha256:
            raise ValueError('O YAML mudou desde a inclusão na fila. Adicione uma nova operação.')


def has_flag(help_text: str, flag: str) -> bool:
    return bool(re.search(r'(?<![\w-])--' + re.escape(flag) + r'(?![\w-])', help_text))


def redact(text: str, token: str) -> str:
    text = ANSI.sub('', text)
    text = text.replace(token, '[TOKEN OCULTO]') if token else text
    # Reduz exposição de credenciais rotuladas, inclusive valores vindos do Archy.
    text = re.sub(r'''(?im)(["']?(?:authToken|access_token|clientSecret|authorization)["']?\s*[:=]\s*)([^\r\n]+)''',
                  r'\1[OCULTO]', text)
    return text


class Invocation:
    """Opções temporárias; o token não é passado na linha de comando."""
    def __init__(self, job: Job, help_text: str):
        job.check_file()
        required = ('file', 'optionsFile', 'authToken', 'authTokenIsClientCredentials', 'location')
        missing = [flag for flag in required if not has_flag(help_text, flag)]
        if missing:
            raise ValueError('Ajuda do Archy não confirmou: ' + ', '.join('--' + x for x in missing)
                             + '. Nenhuma operação foi iniciada.')
        self._temp = tempfile.TemporaryDirectory(prefix='sueth-archy-')
        self.directory = Path(self._temp.name)
        self.options = self.directory / 'options.yaml'
        self.results = self.directory / 'results.json'
        settings = {'authToken': job.token, 'authTokenIsClientCredentials': job.client_credentials,
                    'location': job.region}
        # Sobrescreve configurações persistentes perigosas quando a CLI anuncia suporte.
        for flag in ('debug', 'recreate', 'forceUnlock', 'debugPublish'):
            if has_flag(help_text, flag):
                settings[flag] = False
        try:
            fd = os.open(self.options, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                # JSON scalars também são YAML válidos, incluindo escaping de strings.
                for key, value in settings.items():
                    stream.write(f'{key}: {json.dumps(value, ensure_ascii=False)}\n')
            self.args = [job.operation, '--file', str(job.path), '--optionsFile', str(self.options)]
            if has_flag(help_text, 'resultsFile'):
                self.args += ['--resultsFile', str(self.results)]
        except BaseException:
            self.close()
            raise

    def result_text(self, token: str) -> str:
        if not self.results.is_file():
            return ''
        # Não exibe JSON parcial, que poderia cortar uma credencial no meio.
        if self.results.stat().st_size > 256_000:
            return '[Resultado JSON maior que 256 KB; omitido nesta versão.]'
        return redact(self.results.read_text(encoding='utf-8', errors='replace'), token)

    def close(self) -> None:
        self._temp.cleanup()
