"""Data layer for tirek with two interchangeable backends:

- SupabaseStore: Supabase Postgres over its REST API (used when SUPABASE_URL + SUPABASE_SECRET_KEY are set) — data
  survives every redeploy and is visible in the Supabase dashboard.
- SQLiteStore: local file (development / fallback).

Privacy rules (same for both):
- CV text and "About you" are stored ONLY with opt-in consent (consent_store_cv) and purged after CV_RETENTION_DAYS.
- Consent is explicit, versioned and logged; withdrawing CV consent deletes the stored CV immediately.
- Session tokens are stored as SHA-256 hashes; passwords as PBKDF2 hashes.
- Users can export and delete their data; feedback/events are kept only without the user link after deletion.
- Every admin read of personal data is written to admin_audit.
"""
import hashlib
import json
import sqlite3
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

CONSENT_VERSION = "2026-11-15"
TABLES = ["users", "sessions", "consent_log", "profiles", "state", "reports", "feedback", "events", "admin_audit"]
KEYS = {"users": "id", "sessions": "token_hash", "profiles": "user_id", "state": "user_id"}  # upsert keys

SQLITE_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL, surname TEXT NOT NULL, country TEXT NOT NULL,
  pw_salt TEXT NOT NULL, pw_hash TEXT NOT NULL, created_at INTEGER NOT NULL, last_login_at INTEGER,
  terms_accepted_at INTEGER NOT NULL, consent_version TEXT NOT NULL,
  consent_store_cv INTEGER NOT NULL DEFAULT 0, consent_research INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, expires_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS consent_log (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL, kind TEXT NOT NULL, value INTEGER NOT NULL, version TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS profiles (user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  role_current TEXT, target_role TEXT, target_salary TEXT, study_hours TEXT,
  about TEXT, cv_text TEXT, cv_name TEXT, cv_saved_at INTEGER, updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS state (user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, data TEXT NOT NULL, updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
  created_at INTEGER NOT NULL, rating INTEGER, buy_pro TEXT, comment TEXT);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
  created_at INTEGER NOT NULL, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS admin_audit (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at INTEGER NOT NULL, ip TEXT, action TEXT NOT NULL, target TEXT);
CREATE INDEX IF NOT EXISTS ix_reports_user ON reports(user_id, created_at);
CREATE INDEX IF NOT EXISTS ix_events_name ON events(name);
"""


class StoreError(Exception):
    pass


# ---------------------------------------------------------------- stores
# where: {"col": value} for equality, {"col": ("lt", v)} / ("gt", v) / ("in", [..]) / ("null", True|False)
class SQLiteStore:
    kind = "sqlite"

    def __init__(self, path: Path):
        self.path, self.local, self.lock = path, threading.local(), threading.Lock()
        c = self.conn()
        cols = [r[1] for r in c.execute("PRAGMA table_info(profiles)").fetchall()]
        if "current_role" in cols:  # migrate prototype files created before the rename
            c.execute("ALTER TABLE profiles RENAME COLUMN current_role TO role_current")
        c.executescript(SQLITE_SCHEMA)
        c.commit()

    def conn(self):
        c = getattr(self.local, "c", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=10)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys = ON")
            c.execute("PRAGMA journal_mode = WAL")
            self.local.c = c
        return c

    @staticmethod
    def _where(where):
        sql, args = [], []
        for k, v in (where or {}).items():
            if isinstance(v, tuple):
                op, val = v
                if op == "null":
                    sql.append(f"{k} IS {'' if val else 'NOT '}NULL")
                elif op == "in":
                    sql.append(f"{k} IN ({','.join('?' * len(val)) or 'NULL'})")
                    args += list(val)
                else:
                    sql.append(f"{k} {'<' if op == 'lt' else '>'} ?")
                    args.append(val)
            else:
                sql.append(f"{k} = ?")
                args.append(v)
        return (" WHERE " + " AND ".join(sql)) if sql else "", args

    def select(self, table, where=None, order=None, desc=False, limit=None, cols="*"):
        w, a = self._where(where)
        sql = f"SELECT {cols} FROM {table}{w}" + (f" ORDER BY {order} {'DESC' if desc else 'ASC'}" if order else "") + (f" LIMIT {int(limit)}" if limit else "")
        return [dict(r) for r in self.conn().execute(sql, a).fetchall()]

    def insert(self, table, row):
        with self.lock:
            c = self.conn()
            cur = c.execute(f"INSERT INTO {table} ({','.join(row)}) VALUES ({','.join('?' * len(row))})", list(row.values()))
            c.commit()
            return {**row, "id": row.get("id", cur.lastrowid)}

    def upsert(self, table, row):
        key = KEYS[table]
        sets = ",".join(f"{k}=excluded.{k}" for k in row if k != key)
        with self.lock:
            c = self.conn()
            c.execute(f"INSERT INTO {table} ({','.join(row)}) VALUES ({','.join('?' * len(row))}) ON CONFLICT({key}) DO UPDATE SET {sets}", list(row.values()))
            c.commit()

    def update(self, table, where, values):
        w, a = self._where(where)
        with self.lock:
            c = self.conn()
            c.execute(f"UPDATE {table} SET {','.join(f'{k}=?' for k in values)}{w}", list(values.values()) + a)
            c.commit()

    def delete(self, table, where):
        w, a = self._where(where)
        with self.lock:
            c = self.conn()
            c.execute(f"DELETE FROM {table}{w}", a)
            c.commit()


class SupabaseStore:
    """Supabase Postgres via PostgREST, authenticated with the SECRET (service role) key — backend only."""
    kind = "supabase"

    def __init__(self, url, key, ssl_ctx=None):
        url, key = url.strip().strip('"').strip("'").rstrip("/"), key.strip().strip('"').strip("'")  # tolerate pasted quotes/spaces
        if url.endswith("/rest/v1"):
            url = url[: -len("/rest/v1")]
        if not url.startswith("https://"):
            raise StoreError(f"SUPABASE_URL must start with https:// (got '{url[:40]}')")
        if key.startswith("sb_publishable_") or key.startswith("eyJ") and '"anon"' in key:
            raise StoreError("SUPABASE_SECRET_KEY is the public/publishable key. Use the secret key (sb_secret_…).")
        self.base = url + "/rest/v1/"
        self.key, self.ctx = key, ssl_ctx or ssl.create_default_context()
        missing, other = [], None
        for t in TABLES:  # verify access + schema at startup so problems show on /api/health, not mid-request
            try:
                self.select(t, limit=1, cols="*")
            except StoreError as e:
                msg = str(e)
                if "PGRST205" in msg or "does not exist" in msg:
                    missing.append(t)
                else:
                    other = msg
                    break
        host = url.replace("https://", "")
        if other:
            hint = (" (check SUPABASE_SECRET_KEY: Supabase rejected it)" if "HTTP 401" in other or "HTTP 403" in other
                    else " (check SUPABASE_URL)" if "unreachable" in other or "HTTP 404" in other else "")
            raise StoreError(f"Cannot use Supabase at {host}: {other[:220]}{hint}")
        if missing:
            raise StoreError(f"Supabase at {host} has no tables: " + ", ".join(missing) +
                             ". Run backend/supabase_schema.sql in the SQL Editor of THIS project, then restart.")

    @staticmethod
    def _filters(where):
        q = []
        for k, v in (where or {}).items():
            if isinstance(v, tuple):
                op, val = v
                if op == "null":
                    q.append((k, "is.null" if val else "not.is.null"))
                elif op == "in":
                    q.append((k, "in.(" + ",".join(json.dumps(x) if isinstance(x, str) else str(x) for x in val) + ")"))
                else:
                    q.append((k, f"{op}.{val}"))
            elif v is None:
                q.append((k, "is.null"))
            else:
                q.append((k, f"eq.{v}"))
        return q

    def _req(self, method, table, params=(), body=None, prefer=None):
        url = self.base + table + ("?" + urllib.parse.urlencode(list(params)) if params else "")
        h = {"apikey": self.key, "Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        if prefer:
            h["Prefer"] = prefer
        req = urllib.request.Request(url, method=method, headers=h, data=json.dumps(body).encode() if body is not None else None)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=20, context=self.ctx) as r:
                    raw = r.read()
                    return json.loads(raw) if raw else None
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="ignore")[:300]
                if e.code >= 500 and attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise StoreError(f"Supabase {method} {table}: HTTP {e.code} {detail}")
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise StoreError(f"Supabase unreachable: {e}")

    def select(self, table, where=None, order=None, desc=False, limit=None, cols="*"):
        p = [("select", cols.replace(" ", ""))] + self._filters(where)
        if order:
            p.append(("order", f"{order}.{'desc' if desc else 'asc'}"))
        out, page = [], 1000
        while True:  # PostgREST caps rows per request; page through
            chunk = self._req("GET", table, p + [("limit", min(page, limit - len(out)) if limit else page), ("offset", len(out))])
            out += chunk or []
            if not chunk or len(chunk) < page or (limit and len(out) >= limit):
                return out

    def insert(self, table, row):
        res = self._req("POST", table, body=row, prefer="return=representation")
        return res[0] if res else row

    def upsert(self, table, row):
        self._req("POST", table, params=[("on_conflict", KEYS[table])], body=row, prefer="resolution=merge-duplicates,return=minimal")

    def update(self, table, where, values):
        self._req("PATCH", table, params=self._filters(where), body=values, prefer="return=minimal")

    def delete(self, table, where):
        self._req("DELETE", table, params=self._filters(where), prefer="return=minimal")


# ---------------------------------------------------------------- repository
class DB:
    def __init__(self, store):
        self.s = store
        self.kind = store.kind

    # users & consent
    def create_user(self, u, store_cv, research):
        now = int(time.time())
        self.s.insert("users", {"id": u["id"], "email": u["email"], "name": u["name"], "surname": u["surname"], "country": u["country"],
                                "pw_salt": u["salt"], "pw_hash": u["hash"], "created_at": now, "terms_accepted_at": now,
                                "consent_version": CONSENT_VERSION, "consent_store_cv": int(store_cv), "consent_research": int(research)})
        for kind, val in (("terms", 1), ("store_cv", int(store_cv)), ("research", int(research))):
            self.s.insert("consent_log", {"user_id": u["id"], "created_at": now, "kind": kind, "value": val, "version": CONSENT_VERSION})

    def user_by_email(self, email):
        r = self.s.select("users", {"email": email}, limit=1)
        return r[0] if r else None

    def user_by_id(self, uid):
        r = self.s.select("users", {"id": uid}, limit=1)
        return r[0] if r else None

    def set_consent(self, uid, kind, value):
        col = {"store_cv": "consent_store_cv", "research": "consent_research"}[kind]
        self.s.update("users", {"id": uid}, {col: int(value), "consent_version": CONSENT_VERSION})
        self.s.insert("consent_log", {"user_id": uid, "created_at": int(time.time()), "kind": kind, "value": int(value), "version": CONSENT_VERSION})
        if kind == "store_cv" and not value:  # withdrawing consent deletes the stored CV immediately
            self.s.update("profiles", {"user_id": uid}, {"about": None, "cv_text": None, "cv_name": None, "cv_saved_at": None})

    def delete_user(self, uid):
        self.s.update("feedback", {"user_id": uid}, {"user_id": None})
        self.s.update("events", {"user_id": uid}, {"user_id": None})
        for t in ("sessions", "consent_log", "profiles", "state", "reports"):  # explicit, in case FKs lack ON DELETE CASCADE
            self.s.delete(t, {"user_id": uid})
        self.s.delete("users", {"id": uid})

    # sessions
    @staticmethod
    def _h(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def add_session(self, token, uid, ttl):
        now = int(time.time())
        self.s.insert("sessions", {"token_hash": self._h(token), "user_id": uid, "expires_at": now + ttl})
        self.s.update("users", {"id": uid}, {"last_login_at": now})

    def session_user(self, token):
        if not token:
            return None
        s = self.s.select("sessions", {"token_hash": self._h(token), "expires_at": ("gt", int(time.time()))}, limit=1)
        return self.user_by_id(s[0]["user_id"]) if s else None

    def drop_session(self, token):
        self.s.delete("sessions", {"token_hash": self._h(token or "")})

    # profile / state / reports
    def save_profile(self, uid, inp, cv_text, cv_name, store_cv):
        now, keep = int(time.time()), bool(store_cv)
        old = self.profile(uid) or {}
        row = {"user_id": uid, "role_current": inp.get("currentRole"), "target_role": inp.get("targetRole"),
               "target_salary": inp.get("targetSalary"), "study_hours": inp.get("studyHours"),
               "about": inp.get("about") if keep else None,
               "cv_text": (cv_text or old.get("cv_text")) if keep else None,
               "cv_name": (cv_name if cv_text else old.get("cv_name")) if keep else None,
               "cv_saved_at": (now if (cv_text or inp.get("about")) else old.get("cv_saved_at")) if keep else None,
               "updated_at": now}
        self.s.upsert("profiles", row)

    def profile(self, uid):
        r = self.s.select("profiles", {"user_id": uid}, limit=1)
        return r[0] if r else None

    def state(self, uid):
        r = self.s.select("state", {"user_id": uid}, limit=1)
        return json.loads(r[0]["data"]) if r else {}

    def save_state(self, uid, st):
        self.s.upsert("state", {"user_id": uid, "data": json.dumps(st, ensure_ascii=False), "updated_at": int(time.time())})

    def add_report(self, uid, rep):
        return self.s.insert("reports", {"user_id": uid, "created_at": int(time.time()), "data": json.dumps(rep, ensure_ascii=False)})["id"]

    def reports(self, uid):
        return [{"id": r["id"], **json.loads(r["data"])} for r in self.s.select("reports", {"user_id": uid}, order="id", desc=True)]

    def report(self, uid, rid):
        r = self.s.select("reports", {"user_id": uid, "id": rid}, limit=1)
        return json.loads(r[0]["data"]) if r else None

    # feedback / events / audit
    def add_feedback(self, uid, rating, buy_pro, comment):
        self.s.insert("feedback", {"user_id": uid, "created_at": int(time.time()), "rating": rating, "buy_pro": buy_pro, "comment": comment})

    def event(self, uid, name):
        self.s.insert("events", {"user_id": uid, "created_at": int(time.time()), "name": name})

    def audit(self, ip, action, target=""):
        self.s.insert("admin_audit", {"created_at": int(time.time()), "ip": ip, "action": action, "target": target})

    # per-user export
    def user_export(self, uid):
        return {"consentLog": self.s.select("consent_log", {"user_id": uid}, order="id", cols="created_at,kind,value,version"),
                "feedback": self.s.select("feedback", {"user_id": uid}, cols="created_at,rating,buy_pro,comment"),
                "events": self.s.select("events", {"user_id": uid}, cols="created_at,name")}

    # admin views (aggregated in Python so both backends behave the same)
    def overview(self):
        users = self.s.select("users", cols="id,country,consent_store_cv,consent_research")
        fb = self.s.select("feedback", cols="rating,buy_pro")
        ev = self.s.select("events", cols="name,user_id")
        ratings = [f["rating"] for f in fb if f["rating"] is not None]
        funnel = defaultdict(lambda: {"n": 0, "u": set()})
        for e in ev:
            funnel[e["name"]]["n"] += 1
            if e["user_id"]:
                funnel[e["name"]]["u"].add(e["user_id"])
        return {"users": {"n": len(users), "cv": sum(u["consent_store_cv"] for u in users), "research": sum(u["consent_research"] for u in users)},
                "reports": len(self.s.select("reports", cols="id")),
                "feedback": {"n": len(fb), "avg": round(sum(ratings) / len(ratings), 2) if ratings else None},
                "buyPro": [{"answer": k, "n": v} for k, v in Counter(f["buy_pro"] for f in fb).most_common()],
                "funnel": sorted([{"name": k, "n": v["n"], "users": len(v["u"])} for k, v in funnel.items()], key=lambda x: -x["n"]),
                "countries": [{"country": k, "n": v} for k, v in Counter(u["country"] for u in users).most_common(10)]}

    def feedback_list(self, limit=500):
        fb = self.s.select("feedback", order="id", desc=True, limit=limit)
        ids = list({f["user_id"] for f in fb if f["user_id"]})
        country = {u["id"]: u["country"] for u in (self.s.select("users", {"id": ("in", ids)}, cols="id,country") if ids else [])}
        return [{**f, "country": country.get(f["user_id"]), "user_ref": f["user_id"][:6] if f["user_id"] else None} for f in fb]

    def users_list(self, limit=500):
        users = self.s.select("users", order="created_at", desc=True, limit=limit)
        nrep = Counter(r["user_id"] for r in self.s.select("reports", cols="user_id"))
        has_cv = {p["user_id"] for p in self.s.select("profiles", {"cv_text": ("null", False)}, cols="user_id")}
        return [{k: u[k] for k in ("id", "email", "name", "surname", "country", "created_at", "last_login_at", "consent_store_cv", "consent_research")}
                | {"reports": nrep.get(u["id"], 0), "has_cv": int(u["id"] in has_cv)} for u in users]

    def user_feedback(self, uid):
        return self.s.select("feedback", {"user_id": uid}, cols="created_at,rating,buy_pro,comment")

    def audit_list(self, limit=300):
        return self.s.select("admin_audit", order="id", desc=True, limit=limit)

    def all_tables(self):
        """Every row of every table — used for Excel export and JSON backup."""
        return {t: self.s.select(t, order=("id" if t in ("consent_log", "reports", "feedback", "events", "admin_audit") else None)) for t in TABLES}

    def backup_bytes(self):
        return json.dumps({"exportedAt": int(time.time()), "backend": self.kind, "tables": self.all_tables()}, ensure_ascii=False).encode()

    # retention
    def purge(self, cv_days):
        now = int(time.time())
        self.s.delete("sessions", {"expires_at": ("lt", now)})
        self.s.update("profiles", {"cv_saved_at": ("lt", now - cv_days * 86400)}, {"cv_text": None, "cv_name": None, "about": None, "cv_saved_at": None})


def open_db(data_dir: Path, supabase_url=None, supabase_key=None, ssl_ctx=None):
    if supabase_url and supabase_key:
        return DB(SupabaseStore(supabase_url, supabase_key, ssl_ctx))
    return DB(SQLiteStore(data_dir / "tirek.db"))
