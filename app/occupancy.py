"""Anonymous per-image editing leases, atomic across threads/processes on Windows."""
import json
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from shared_masks import check_name, pointer


class Occupied(ValueError):
    pass


class Occupancy:
    def __init__(self, root, ttl=90, clock=time.time):
        self.root = Path(root)
        self.path = self.root / '_occupancy.sqlite3'
        self.ttl, self.clock = ttl, clock
        self.root.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS leases (site TEXT, stem TEXT, client TEXT, token TEXT, expires REAL, PRIMARY KEY(site,stem))')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db

    @contextmanager
    def transaction(self):
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.execute('COMMIT')
        except BaseException:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise
        finally:
            db.close()

    @staticmethod
    def credential(value):
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,100}', value):
            raise ValueError('无效占用凭证')
        return value

    def revision(self, site, stem):
        p = pointer(self.root, site, stem)
        return json.loads(p.read_text(encoding='utf-8')).get('revision') if p.exists() else None

    def active(self, db, site, stem):
        row = db.execute('SELECT * FROM leases WHERE site=? AND stem=?', (site, stem)).fetchone()
        return row if row and row['expires'] > self.clock() else None

    def operate(self, action, site, stem, client=None, token=None):
        check_name(site); check_name(stem)
        if action not in ('acquire', 'heartbeat', 'release'):
            raise ValueError('无效占用操作')
        if action == 'acquire':
            self.credential(client)
        else:
            self.credential(token)
        with self.transaction() as db:
            row = self.active(db, site, stem)
            if action == 'release':
                db.execute('DELETE FROM leases WHERE site=? AND stem=? AND token=?', (site, stem, token))
                return {'released': True}
            mine = row and (row['client'] == client if action == 'acquire' else secrets.compare_digest(row['token'], token))
            if (row and not mine) or (action == 'heartbeat' and not mine):
                return {'owned': False, 'occupied': bool(row), 'expires_in': max(0, row['expires'] - self.clock()) if row else 0}
            actual_token = row['token'] if mine else secrets.token_hex(24)
            actual_client = row['client'] if mine else client
            db.execute('INSERT OR REPLACE INTO leases VALUES (?,?,?,?,?)', (site, stem, actual_client, actual_token, self.clock() + self.ttl))
            return {'owned': True, 'token': actual_token, 'expires_in': self.ttl, 'revision': self.revision(site, stem)}

    def status(self, site):
        check_name(site)
        db = self.connect()
        try:
            rows = db.execute('SELECT stem,expires FROM leases WHERE site=? AND expires>?', (site, self.clock())).fetchall()
            return {'site': site, 'items': [{'stem': r['stem'], 'occupied': True} for r in rows]}
        finally:
            db.close()

    @contextmanager
    def saving(self, site, stem, token, legacy=False):
        check_name(site); check_name(stem)
        if not legacy:
            self.credential(token)
        with self.transaction() as db:
            row = self.active(db, site, stem)
            if legacy:
                if row:
                    raise Occupied('此影像有人正在标注，旧页面无法保存。请保留当前页面，不要刷新丢弃未保存修改。')
            elif not row or not secrets.compare_digest(row['token'], token):
                raise Occupied('编辑占用已失效或已由其他窗口接手，当前修改仍保留在页面中，请重新申请编辑权。')
            yield
            if row and not legacy:
                db.execute('UPDATE leases SET expires=? WHERE site=? AND stem=? AND token=?', (self.clock() + self.ttl, site, stem, token))
