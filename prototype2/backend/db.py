"""SQLite data layer for tirek (stdlib sqlite3).

Privacy principles built into the schema:
- Data minimisation: CV text and the free-text "about you" are stored ONLY if the user opts in (consent_store_cv),
  and are purged automatically after CV_RETENTION_DAYS.
- Consent is explicit, versioned and logged (consent_log), and can be withdrawn at any time.
- Session tokens are stored as SHA-256 hashes; passwords as PBKDF2 hashes.
- Users can export all their data and delete their account (hard delete; feedback is kept only as anonymous text).
- Every admin read of personal data is written to admin_audit.
"""
import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path

CONSENT_VERSION = "2026-11-15"
SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL, surname TEXT NOT NULL, country TEXT NOT NULL,
  pw_salt TEXT NOT NULL, pw_hash TEXT NOT NULL, created_at INTEGER NOT NULL, last_login_at INTEGER,
  terms_accepted_at INTEGER NOT NULL, consent_version TEXT NOT NULL,
  consent_store_cv INTEGER NOT NULL DEFAULT 0,      -- keep CV text + "about you" to prefill and compare reports
  consent_research INTEGER NOT NULL DEFAULT 0       -- allow anonymised, aggregated use for product research
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS consent_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL, kind TEXT NOT NULL, value INTEGER NOT NULL, version TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS profiles (
  user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  current_role TEXT, target_role TEXT, target_salary TEXT, study_hours TEXT,
  about TEXT, cv_text TEXT, cv_name TEXT, cv_saved_at INTEGER,   -- only when consent_store_cv = 1
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS state (                    -- current report / roadmap / interview for the app
  user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, data TEXT NOT NULL, updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS reports (                  -- every generated report (history + PDF source)
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL, data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
  created_at INTEGER NOT NULL, rating INTEGER, buy_pro TEXT, comment TEXT
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
  created_at INTEGER NOT NULL, name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS admin_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT, created_at INTEGER NOT NULL, ip TEXT, action TEXT NOT NULL, target TEXT
);
CREATE INDEX IF NOT EXISTS ix_reports_user ON reports(user_id, created_at);
CREATE INDEX IF NOT EXISTS ix_events_name ON events(name);
"""


class DB:
    def __init__(self, path: Path):
        self.path = path
        self.local = threading.local()
        self.lock = threading.Lock()
        with self.conn() as c:
            c.executescript(SCHEMA)

    def conn(self):
        c = getattr(self.local, "c", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=10)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys = ON")
            c.execute("PRAGMA journal_mode = WAL")
            self.local.c = c
        return c

    def q(self, sql, args=()):
        return [dict(r) for r in self.conn().execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        r = self.conn().execute(sql, args).fetchone()
        return dict(r) if r else None

    def run(self, sql, args=()):
        with self.lock:
            c = self.conn()
            cur = c.execute(sql, args)
            c.commit()
            return cur.lastrowid

    # ---------- users & consent ----------
    def create_user(self, u, store_cv, research):
        now = int(time.time())
        with self.lock:
            c = self.conn()
            c.execute("INSERT INTO users (id,email,name,surname,country,pw_salt,pw_hash,created_at,terms_accepted_at,consent_version,"
                      "consent_store_cv,consent_research) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                      (u["id"], u["email"], u["name"], u["surname"], u["country"], u["salt"], u["hash"], now, now, CONSENT_VERSION,
                       int(store_cv), int(research)))
            for kind, val in (("terms", 1), ("store_cv", int(store_cv)), ("research", int(research))):
                c.execute("INSERT INTO consent_log (user_id,created_at,kind,value,version) VALUES (?,?,?,?,?)", (u["id"], now, kind, val, CONSENT_VERSION))
            c.commit()

    def user_by_email(self, email):
        return self.one("SELECT * FROM users WHERE email=?", (email,))

    def user_by_id(self, uid):
        return self.one("SELECT * FROM users WHERE id=?", (uid,))

    def set_consent(self, uid, kind, value):
        col = {"store_cv": "consent_store_cv", "research": "consent_research"}[kind]
        now = int(time.time())
        with self.lock:
            c = self.conn()
            c.execute(f"UPDATE users SET {col}=?, consent_version=? WHERE id=?", (int(value), CONSENT_VERSION, uid))
            c.execute("INSERT INTO consent_log (user_id,created_at,kind,value,version) VALUES (?,?,?,?,?)", (uid, now, kind, int(value), CONSENT_VERSION))
            if kind == "store_cv" and not value:  # withdrawing consent deletes the stored CV immediately
                c.execute("UPDATE profiles SET about=NULL, cv_text=NULL, cv_name=NULL, cv_saved_at=NULL WHERE user_id=?", (uid,))
            c.commit()

    def delete_user(self, uid):
        with self.lock:
            c = self.conn()
            c.execute("UPDATE feedback SET user_id=NULL WHERE user_id=?", (uid,))
            c.execute("UPDATE events SET user_id=NULL WHERE user_id=?", (uid,))
            c.execute("DELETE FROM users WHERE id=?", (uid,))  # cascades to sessions, consent_log, profiles, state, reports
            c.commit()

    # ---------- sessions ----------
    @staticmethod
    def _h(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def add_session(self, token, uid, ttl):
        self.run("INSERT INTO sessions (token_hash,user_id,expires_at) VALUES (?,?,?)", (self._h(token), uid, int(time.time()) + ttl))
        self.run("UPDATE users SET last_login_at=? WHERE id=?", (int(time.time()), uid))

    def session_user(self, token):
        if not token:
            return None
        return self.one("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?",
                        (self._h(token), int(time.time())))

    def drop_session(self, token):
        self.run("DELETE FROM sessions WHERE token_hash=?", (self._h(token or ""),))

    # ---------- profile / state / reports ----------
    def save_profile(self, uid, inp, cv_text, cv_name, store_cv):
        now = int(time.time())
        keep = bool(store_cv)
        self.run("INSERT INTO profiles (user_id,current_role,target_role,target_salary,study_hours,about,cv_text,cv_name,cv_saved_at,updated_at) "
                 "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET current_role=excluded.current_role, "
                 "target_role=excluded.target_role, target_salary=excluded.target_salary, study_hours=excluded.study_hours, "
                 "about=excluded.about, cv_text=COALESCE(excluded.cv_text, profiles.cv_text), cv_name=COALESCE(excluded.cv_name, profiles.cv_name), "
                 "cv_saved_at=COALESCE(excluded.cv_saved_at, profiles.cv_saved_at), updated_at=excluded.updated_at",
                 (uid, inp.get("currentRole"), inp.get("targetRole"), inp.get("targetSalary"), inp.get("studyHours"),
                  inp.get("about") if keep else None, (cv_text or None) if keep else None, (cv_name or None) if keep and cv_text else None,
                  now if keep and (cv_text or inp.get("about")) else None, now))

    def profile(self, uid):
        return self.one("SELECT * FROM profiles WHERE user_id=?", (uid,))

    def state(self, uid):
        r = self.one("SELECT data FROM state WHERE user_id=?", (uid,))
        return json.loads(r["data"]) if r else {}

    def save_state(self, uid, st):
        self.run("INSERT INTO state (user_id,data,updated_at) VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                 (uid, json.dumps(st, ensure_ascii=False), int(time.time())))

    def add_report(self, uid, rep):
        return self.run("INSERT INTO reports (user_id,created_at,data) VALUES (?,?,?)", (uid, int(time.time()), json.dumps(rep, ensure_ascii=False)))

    def reports(self, uid):
        return [{"id": r["id"], **json.loads(r["data"])} for r in self.q("SELECT id,data FROM reports WHERE user_id=? ORDER BY id DESC", (uid,))]

    def report(self, uid, rid):
        r = self.one("SELECT data FROM reports WHERE user_id=? AND id=?", (uid, rid))
        return json.loads(r["data"]) if r else None

    # ---------- feedback / events / audit ----------
    def add_feedback(self, uid, rating, buy_pro, comment):
        self.run("INSERT INTO feedback (user_id,created_at,rating,buy_pro,comment) VALUES (?,?,?,?,?)", (uid, int(time.time()), rating, buy_pro, comment))

    def event(self, uid, name):
        self.run("INSERT INTO events (user_id,created_at,name) VALUES (?,?,?)", (uid, int(time.time()), name))

    def audit(self, ip, action, target=""):
        self.run("INSERT INTO admin_audit (created_at,ip,action,target) VALUES (?,?,?,?)", (int(time.time()), ip, action, target))

    # ---------- backup ----------
    def backup_bytes(self):
        """Consistent copy of the whole database (safe while the app is running)."""
        import os
        import tempfile
        fd, tmp = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            dst = sqlite3.connect(tmp)
            with self.lock:
                self.conn().backup(dst)
            dst.close()
            return Path(tmp).read_bytes()
        finally:
            os.remove(tmp)

    # ---------- retention ----------
    def purge(self, cv_days):
        now = int(time.time())
        self.run("DELETE FROM sessions WHERE expires_at<?", (now,))
        self.run("UPDATE profiles SET cv_text=NULL, cv_name=NULL, about=NULL, cv_saved_at=NULL WHERE cv_saved_at IS NOT NULL AND cv_saved_at<?",
                 (now - cv_days * 86400,))
