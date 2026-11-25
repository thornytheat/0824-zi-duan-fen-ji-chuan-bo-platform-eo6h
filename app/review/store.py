import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from app.business import DomainIssue

SCHEMA = '''CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, report TEXT NOT NULL, created TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING', revision INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '', reviewed TEXT
);
CREATE TABLE IF NOT EXISTS revocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    field INTEGER NOT NULL,
    day INTEGER NOT NULL,
    label INTEGER,
    created TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_revocations_run ON revocations(run_id, day);
CREATE TABLE IF NOT EXISTS sources (
    run_id TEXT PRIMARY KEY,
    data BLOB NOT NULL
);
'''


class Store:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=15)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA busy_timeout=15000')
            db.executescript(SCHEMA)
            yield db

    def register(self, run_id, report, source=b''):
        with self.connect() as db:
            db.execute('INSERT INTO runs(id,report,created) VALUES (?,?,?) ON CONFLICT(id) DO NOTHING',
                       (run_id,json.dumps(report,ensure_ascii=False),report['manifest']['created']))
            db.execute('INSERT INTO sources(run_id,data) VALUES (?,?) ON CONFLICT(run_id) DO NOTHING',
                       (run_id, sqlite3.Binary(source)))
        return self.load(run_id)

    def load(self, run_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM runs WHERE id=?',(run_id,)).fetchone()
        if row is None:
            raise DomainIssue('RUN_NOT_FOUND')
        result = dict(row)
        result['report'] = json.loads(result['report'])
        return result

    def list(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT id,created,status,revision,note FROM runs ORDER BY created DESC,id LIMIT 50')]

    def revocations(self, run_id):
        with self.connect() as db:
            rows = db.execute('SELECT case_id, field, day, label FROM revocations WHERE run_id=? ORDER BY id',
                              (run_id,)).fetchall()
        return [dict(case=row['case_id'], field=int(row['field']), day=row['day'], label=row['label']) for row in rows]

    @contextmanager
    def transaction(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=15)) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA busy_timeout=15000')
            db.executescript(SCHEMA)
            db.execute('BEGIN IMMEDIATE')
            try:
                yield db
            except Exception:
                db.rollback()
                raise
            else:
                db.commit()

    def add_revocation(self, db, run_id, entry, now):
        db.execute('INSERT INTO revocations(run_id,case_id,field,day,label,created) VALUES (?,?,?,?,?,?)',
                   (run_id, entry['case'], entry['field'], entry['day'], entry.get('label'), now))

    def update_report(self, db, run_id, report, status=None, note=None, reviewed=None):
        current = db.execute('SELECT revision FROM runs WHERE id=?', (run_id,)).fetchone()
        if current is None:
            raise DomainIssue('RUN_NOT_FOUND')
        if status is None:
            db.execute('UPDATE runs SET report=? WHERE id=?', (json.dumps(report, ensure_ascii=False), run_id))
        else:
            db.execute('UPDATE runs SET report=?,status=?,note=?,reviewed=?,revision=revision+1 WHERE id=?',
                       (json.dumps(report, ensure_ascii=False), status, note, reviewed, run_id))
        return current['revision']
