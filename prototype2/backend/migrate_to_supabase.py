"""Copy a tirek backup into Supabase (one-time migration).

    python3 migrate_to_supabase.py ~/Downloads/tirek-backup-XXXX.db      # or .json from the admin page

Needs SUPABASE_URL and SUPABASE_SECRET_KEY (read from .env) and the tables from supabase_schema.sql.
Existing users (same id or email) are skipped, so it is safe to run twice. Sessions are not copied (users log in again).
"""
import os
import sys
from pathlib import Path

from db import SupabaseStore
from export_excel import load_tables

ROOT = Path(__file__).resolve().parent
for line in (ROOT / ".env").read_text().splitlines() if (ROOT / ".env").exists() else []:
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

if len(sys.argv) < 2:
    sys.exit(__doc__)
url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SECRET_KEY")
if not (url and key):
    sys.exit("Set SUPABASE_URL and SUPABASE_SECRET_KEY in backend/.env first.")

try:
    import certifi, ssl  # noqa: E401
    ctx = ssl.create_default_context(cafile=certifi.where())
except Exception:
    ctx = None
store = SupabaseStore(url, key, ctx)
tables = load_tables(sys.argv[1])

existing = {u["id"] for u in store.select("users", cols="id")} | {u["email"] for u in store.select("users", cols="email")}
users = [u for u in tables.get("users", []) if u["id"] not in existing and u["email"] not in existing]
new_ids = {u["id"] for u in users}
print(f"Users in backup: {len(tables.get('users', []))}, new to copy: {len(users)}")


def copy(name, rows, drop_id=True):
    rows = [{k: v for k, v in r.items() if not (drop_id and k == "id")} for r in rows]
    for i in range(0, len(rows), 200):
        if rows[i:i + 200]:
            store._req("POST", name, body=rows[i:i + 200], prefer="return=minimal")
    print(f"  {name}: {len(rows)}")


copy("users", users, drop_id=False)
mine = lambda t: [r for r in tables.get(t, []) if r.get("user_id") in new_ids]
copy("consent_log", mine("consent_log"))
copy("profiles", mine("profiles"), drop_id=False)
copy("state", mine("state"), drop_id=False)
copy("reports", mine("reports"))
# feedback/events of deleted users have user_id = NULL: copy them once (only when the backup brings new users or none exist yet)
anon = lambda t: [r for r in tables.get(t, []) if r.get("user_id") is None] if users else []
copy("feedback", mine("feedback") + anon("feedback"))
copy("events", mine("events") + anon("events"))
copy("admin_audit", tables.get("admin_audit", []) if users else [])
print("Done. Users need to log in again (sessions are not copied).")
