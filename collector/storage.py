import json
import sqlite3
from pathlib import Path


def key(entry):
    return json.dumps(entry, sort_keys=True)


class Storage:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS pages (
            job_key TEXT PRIMARY KEY, page_name TEXT NOT NULL, page_url TEXT NOT NULL,
            website_url TEXT NOT NULL, status TEXT NOT NULL, error_reason TEXT NOT NULL,
            collected_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS observations (
            job_key TEXT NOT NULL REFERENCES pages(job_key) ON DELETE CASCADE,
            email TEXT NOT NULL, source_url TEXT NOT NULL,
            PRIMARY KEY(job_key, email, source_url));
        ''')

    def done(self, job_key, retry_failed=False):
        row = self.db.execute("SELECT status FROM pages WHERE job_key=?", (job_key,)).fetchone()
        return bool(row and (not retry_failed or row[0] in {"ok", "no_email"}))

    def save(self, job_key, result):
        # Atomic per-Page checkpoint. An interrupted Page is safely re-collected.
        with self.db:
            self.db.execute("DELETE FROM pages WHERE job_key=?", (job_key,))
            self.db.execute("INSERT INTO pages VALUES (?,?,?,?,?,?,?)", (
                job_key, result.page_name, result.page_url, result.website_url,
                result.status, result.error_reason, result.collected_at))
            self.db.executemany("INSERT INTO observations VALUES (?,?,?) ON CONFLICT(job_key,email,source_url) DO NOTHING",
                                ((job_key, email, source) for email, source in result.observations))

    def rows(self, keys):
        # Only export the current configured batch, not unrelated historic jobs.
        for job_key in dict.fromkeys(keys):
            yield from self.db.execute('''SELECT p.page_name,p.page_url,p.website_url,
                COALESCE(o.email,''),COALESCE(o.source_url,''),p.status,p.error_reason,p.collected_at
                FROM pages p LEFT JOIN observations o USING(job_key) WHERE p.job_key=?
                ORDER BY o.email,o.source_url''', (job_key,))

    def close(self):
        self.db.close()
