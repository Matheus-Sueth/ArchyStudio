from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .core import Job


class History:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute('''CREATE TABLE IF NOT EXISTS executions (
            id TEXT PRIMARY KEY, started TEXT, operation TEXT, filename TEXT,
            region TEXT, status TEXT, exit_code INTEGER, sha256 TEXT)''')
        # Um fechamento inesperado não confirma o estado remoto.
        self.db.execute("UPDATE executions SET status='Interrompido / desconhecido' WHERE status='Executando'")
        self.db.commit()

    def start(self, job: Job):
        self.db.execute('INSERT INTO executions VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                        (job.id, datetime.now(timezone.utc).isoformat(timespec='seconds'), job.operation,
                         job.path.name, job.region, 'Executando', None, job.sha256))
        self.db.commit()

    def finish(self, job_id: str, status: str, exit_code: int | None):
        self.db.execute('UPDATE executions SET status=?, exit_code=? WHERE id=?', (status, exit_code, job_id))
        self.db.commit()

    def recent(self):
        return self.db.execute('SELECT started, operation, filename, region, status, exit_code '
                               'FROM executions ORDER BY started DESC LIMIT 200').fetchall()

    def close(self):
        self.db.close()
