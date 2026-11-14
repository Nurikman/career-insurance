"""Build an Excel workbook from the tirek database.

Used by the admin endpoint /api/admin/export.xlsx and as a command-line converter for a downloaded backup:

    python3 export_excel.py tirek-backup-20261115-1200.json   # or an older .db backup -> .xlsx next to it
"""
import json
import sqlite3
import sys
import time
from pathlib import Path

from xlsx import workbook


def _t(ts):
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts)) if ts else ""


def _yn(v):
    return "yes" if v else "no"


def _rows(tables, name, key="created_at", desc=False):
    return sorted(tables.get(name) or [], key=lambda r: (r.get(key) is None, r.get(key) or 0), reverse=desc)


def load_tables(path):
    """Read a backup: .json (current admin backup) or .db (older SQLite backup)."""
    path = Path(path)
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))["tables"]
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    tables = {t: [dict(r) for r in conn.execute(f"SELECT * FROM {t}")] for t in names if not t.startswith("sqlite_")}
    for r in tables.get("profiles", []):  # older files used current_role
        if "current_role" in r:
            r["role_current"] = r.pop("current_role")
    return tables


def build(tables):
    """tables: {table name: [row dicts]} -> .xlsx bytes."""
    users = _rows(tables, "users")
    email = {u["id"]: u["email"] for u in users}
    nrep = {}
    for r in tables.get("reports") or []:
        nrep[r["user_id"]] = nrep.get(r["user_id"], 0) + 1

    s_users = [[u["id"], u["name"], u["surname"], u["email"], u["country"], _t(u["created_at"]), _t(u["last_login_at"]),
                _yn(u["consent_store_cv"]), _yn(u["consent_research"]), u["consent_version"], nrep.get(u["id"], 0)] for u in users]

    s_profiles = [[email.get(p["user_id"], p["user_id"]), p.get("role_current"), p["target_role"], p["target_salary"], p["study_hours"],
                   p["cv_name"], _t(p["cv_saved_at"]), p["about"], p["cv_text"], _t(p["updated_at"])]
                  for p in _rows(tables, "profiles", "updated_at", True)]

    s_reports, s_vac = [], []
    for r in _rows(tables, "reports", desc=True):
        d = json.loads(r["data"])
        v, rk, pr = d.get("value") or {}, d.get("risk") or {}, d.get("profile") or {}
        s_reports.append([
            r["id"], email.get(r["user_id"], "deleted user"), _t(r["created_at"]), d.get("currentRole"), d.get("targetRole"),
            d.get("targetSalary"), rk.get("score"), rk.get("level"), v.get("min"), v.get("max"), v.get("median"), v.get("readiness"),
            (v.get("potential") or {}).get("max"), pr.get("years_experience"), "; ".join(pr.get("education") or []),
            ", ".join(d.get("skills") or []),
            ", ".join(x.get("skill", "") for x in d.get("growing") or []), ", ".join(x.get("skill", "") for x in d.get("declining") or []),
            "; ".join(f"{a['role']} {a['match']}%" for a in d.get("alternatives") or []),
            " | ".join(f"{p.get('period')}: {p.get('focus')}" for p in d.get("protectionPlan") or [])])
        for j in (d.get("vacancies") or [])[:15]:
            sy = j.get("salaryYear") or {}
            s_vac.append([r["id"], email.get(r["user_id"], "deleted user"), j.get("title"), j.get("company"), j.get("role"),
                          sy.get("min"), sy.get("max"), j.get("fit"), ", ".join(j.get("missing") or []), j.get("url")])

    s_feedback = [[_t(f["created_at"]), email.get(f["user_id"], "anonymous"), f["rating"], f["buy_pro"], f["comment"]]
                  for f in _rows(tables, "feedback", desc=True)]
    s_events = [[_t(e["created_at"]), email.get(e["user_id"], "anonymous"), e["name"]] for e in _rows(tables, "events", desc=True)]
    s_consent = [[_t(c["created_at"]), email.get(c["user_id"], c["user_id"]), c["kind"], _yn(c["value"]), c["version"]]
                 for c in _rows(tables, "consent_log", desc=True)]
    s_audit = [[_t(a["created_at"]), a["action"], a["target"], a["ip"]] for a in _rows(tables, "admin_audit", desc=True)]

    return workbook([
        ("Users", ["User ID", "Name", "Surname", "Email", "Country", "Signed up (UTC)", "Last login (UTC)", "CV consent", "Research consent",
                   "Consent version", "Reports"], s_users),
        ("Reports", ["Report ID", "User", "Created (UTC)", "Current role", "Target role", "Target salary", "Risk score", "Risk level",
                     "Value min $", "Value max $", "Value median $", "Readiness %", "Potential max $", "Years experience", "Education",
                     "Skills", "Growing skills", "Declining skills", "Alternatives (match)", "90-day plan"], s_reports),
        ("Feedback", ["Date (UTC)", "User", "Usefulness 1-5", "Would buy Pro", "Comment"], s_feedback),
        ("Profiles & CV", ["User", "Current role", "Target role", "Target salary", "Study time", "CV file", "CV saved (UTC)",
                           "About you (consented only)", "CV text (consented only)", "Updated (UTC)"], s_profiles),
        ("Report vacancies", ["Report ID", "User", "Title", "Company", "Role", "Salary min $", "Salary max $", "Fit %", "Missing skills", "URL"], s_vac),
        ("Events", ["Date (UTC)", "User", "Event"], s_events),
        ("Consent log", ["Date (UTC)", "User", "Consent", "Given", "Version"], s_consent),
        ("Admin access log", ["Date (UTC)", "Action", "Target", "IP"], s_audit),
    ])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python3 export_excel.py <backup.json|backup.db> [output.xlsx]")
    src = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_suffix(".xlsx")
    out.write_bytes(build(load_tables(src)))
    print(f"Saved {out}  (contains personal data — keep it private)")
