"""tirek — Career Insurance API (prototype 2).

Zero dependencies: Python 3.9+ standard library only.
Local:   python3 server.py  ->  http://localhost:8000  (also serves ../frontend)
Railway: set OPENAI_API_KEY, DATA_DIR=/data (volume), ALLOWED_ORIGINS=https://<app>.vercel.app
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import ssl
import statistics
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent


# ---------- config ----------
def load_env():
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()
STATIC = ROOT / "data"                                                   # bundled read-only data (jobs, taxonomy)
DATA = Path(os.environ.get("DATA_DIR") or ROOT / "data")                 # writable: users, sessions, reports (Railway volume)
PUBLIC = Path(os.environ.get("FRONTEND_DIR") or ROOT.parent / "frontend")  # served only when present (local dev)
LOGS, USERDATA = DATA / "logs", DATA / "userdata"
for d in (LOGS, USERDATA):
    d.mkdir(parents=True, exist_ok=True)
ALLOWED_ORIGINS = {o.strip().rstrip("/") for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()}
COOKIE_ATTRS = "SameSite=None; Secure" if os.environ.get("CROSS_SITE_COOKIES") == "1" else "SameSite=Lax"
OPENAI_KEY =os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
LLM_CALLS_PER_HOUR = int(os.environ.get("LLM_CALLS_PER_HOUR", "80"))
# Reasoning models (gpt-5+/o-series) spend output tokens on hidden reasoning; "none" keeps answers fast and complete.
# Parameters a model rejects are switched off automatically on the first call and remembered.
MODEL_PARAMS = {"tokens_key": "max_completion_tokens", "temperature": True,
                "effort": os.environ.get("OPENAI_REASONING_EFFORT", "none").strip() or None}
MAX_BODY = 1_000_000

TAX = json.loads((STATIC / "taxonomy.json").read_text(encoding="utf-8"))
SKILLS, ROLES = TAX["skills"], TAX["roles"]
SKILL_NAMES = sorted(SKILLS)
SKILL_LOWER = {s.lower(): s for s in SKILLS}
RUBRIC = ["Technical correctness", "Reasoning", "Evidence / examples", "Clarity"]
WEIGHTS = {"A": 0.30, "D": 0.25, "G": 0.25, "C": 0.20}  # R = 0.3A + 0.25D + 0.25G + 0.2C


def load_jobs():
    f = STATIC / "jobs_us.json"
    if not f.exists():
        return {"meta": {"count": 0, "note": "No jobs scraped yet: run python3 scraper/scrape_us_jobs.py"}, "jobs": []}
    return json.loads(f.read_text(encoding="utf-8"))


JOBS = load_jobs()


def ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    if Path("/etc/ssl/cert.pem").exists():
        return ssl.create_default_context(cafile="/etc/ssl/cert.pem")
    return ssl.create_default_context()


SSL_CTX = ssl_context()
_calls = defaultdict(list)
_lock = threading.Lock()


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


# ---------- storage ----------
def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path, obj):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


USERS_F, SESS_F = DATA / "users.json", DATA / "sessions.json"


def user_state(uid):
    return read_json(USERDATA / f"{uid}.json", {})


def save_state(uid, st):
    write_json(USERDATA / f"{uid}.json", st)


def hash_pw(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()


def public_user(u):
    return {k: u[k] for k in ("id", "name", "surname", "country", "email")}


# ---------- LLM ----------
def llm_json(uid, system, user, max_tokens=1200):
    if not OPENAI_KEY:
        raise ApiError(503, "AI is not configured: add OPENAI_API_KEY to prototype1/.env and restart the server.")
    now = time.time()
    with _lock:
        _calls[uid] = [t for t in _calls[uid] if now - t < 3600]
        if len(_calls[uid]) >= LLM_CALLS_PER_HOUR:
            raise ApiError(429, "AI usage limit reached for this hour. Please try again later.")
        _calls[uid].append(now)
    budget = max_tokens
    for attempt in range(5):
        body = {"model": OPENAI_MODEL, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "response_format": {"type": "json_object"}, MODEL_PARAMS["tokens_key"]: budget}
        if MODEL_PARAMS["temperature"]:
            body["temperature"] = 0.2
        if MODEL_PARAMS["effort"]:
            body["reasoning_effort"] = MODEL_PARAMS["effort"]
        req = urllib.request.Request(OPENAI_URL, data=json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=90, context=SSL_CTX) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="ignore")[:600]
            if e.code == 400:  # learn which parameters this model accepts, remember it for later calls
                if "max_tokens" in detail and MODEL_PARAMS["tokens_key"] == "max_tokens":
                    MODEL_PARAMS["tokens_key"] = "max_completion_tokens"
                    continue
                if "temperature" in detail and MODEL_PARAMS["temperature"]:
                    MODEL_PARAMS["temperature"] = False
                    continue
                if "reasoning_effort" in detail and MODEL_PARAMS["effort"]:
                    MODEL_PARAMS["effort"] = None
                    continue
            if e.code == 401:
                raise ApiError(502, "OpenAI rejected the API key. Check OPENAI_API_KEY in .env.")
            print("OpenAI HTTP error", e.code, detail[:200])
            raise ApiError(502, f"AI service error ({e.code}). Please retry.")
        except (urllib.error.URLError, TimeoutError):
            raise ApiError(504, "AI service is unreachable or timed out. Please retry.")
        try:
            choice = data["choices"][0]
            text = choice["message"].get("content") or ""
        except (KeyError, IndexError, TypeError):
            raise ApiError(502, "AI returned an invalid response. Please retry.")
        parsed = parse_json(text)
        if parsed is not None:
            return parsed
        if choice.get("finish_reason") == "length" and budget < 12000:
            print(f"LLM output cut at {budget} tokens; retrying with a larger budget")
            budget *= 2
            continue
        print("LLM returned non-JSON content, finish_reason:", choice.get("finish_reason"))
        raise ApiError(502, "AI returned an invalid response. Please retry.")
    raise ApiError(502, "AI request failed. Please retry.")


def parse_json(text):
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        a, b = text.find("{"), text.rfind("}")  # tolerate code fences / stray text around the JSON
        if a != -1 and b > a:
            try:
                return json.loads(text[a:b + 1])
            except json.JSONDecodeError:
                return None
    return None


def strs(x, n=10, ln=200):
    return [str(i)[:ln] for i in (x or []) if str(i).strip()][:n] if isinstance(x, list) else []


def canon(name):
    return SKILL_LOWER.get(str(name or "").strip().lower())


# ---------- skills ----------
def keyword_skills(text):
    low = " " + text.lower() + " "
    found = set()
    for skill, meta in SKILLS.items():
        names = meta["aliases"] + ([] if skill in ("R", "Go") else [skill])
        for a in names:
            if re.search(r"(?<![a-z0-9])" + re.escape(a.lower()) + r"(?![a-z0-9])", low):
                found.add(skill)
                break
    return found


# ---------- market data (from scraped real postings) ----------
def role_stats(role):
    jobs = [j for j in JOBS["jobs"] if j["role"] == role]
    freq = defaultdict(float)
    for j in jobs:
        for s in j.get("mandatory", []):
            freq[s] += 1
        for s in j.get("preferred", []):
            freq[s] += 0.5
    top = sorted(freq.items(), key=lambda x: -x[1])[:10]
    sal = []
    for j in jobs:
        s = j.get("salary")
        if s and s.get("min"):
            k = 2080 if s.get("period") == "hour" else 1
            sal.append((s["min"] + (s.get("max") or s["min"])) / 2 * k)
    return {
        "role": role, "vacancies": len(jobs),
        "topSkills": [{"skill": k, "share": round(v / max(len(jobs), 1), 2)} for k, v in top],
        "salary": {"n": len(sal), "median": round(statistics.median(sal)), "min": round(min(sal)), "max": round(max(sal))} if sal else None,
    }


def match_pct(have, stats):
    tot = sum(t["share"] for t in stats["topSkills"])
    if not tot:
        return 0
    return round(100 * sum(t["share"] for t in stats["topSkills"] if t["skill"] in have) / tot)


def risk_score(have, current_role, target_role):
    """Fixed backend formula: R = 0.3A + 0.25D + 0.25G + 0.2C (each factor 0..1)."""
    role = ROLES.get(current_role, {"A": 0.5, "trend": 0.5})
    n = max(len(JOBS["jobs"]), 1)
    demand = defaultdict(int)
    for j in JOBS["jobs"]:
        for s in set(j.get("mandatory", []) + j.get("preferred", [])):
            demand[s] += 1
    low_demand = [s for s in have if demand[s] / n < 0.03]
    A = role["A"]
    D = 0.5 * role["trend"] + 0.5 * (len(low_demand) / len(have) if have else 1)
    G = 1 - match_pct(have, role_stats(target_role)) / 100
    domains = {SKILLS[s]["domain"] for s in have if SKILLS[s]["domain"] != "soft"}
    C = max(0.0, 1 - (len(domains) - 1) / 4) if domains else 1.0
    f = {"A": A, "D": D, "G": G, "C": C}
    R = sum(WEIGHTS[k] * f[k] for k in f)
    score = round(R * 100)
    return {
        "score": score, "level": "Low risk" if score < 35 else "Medium risk" if score < 65 else "High risk",
        "factors": [
            {"key": k, "name": nm, "weight": WEIGHTS[k], "value": round(f[k], 2), "contribution": round(100 * WEIGHTS[k] * f[k])}
            for k, nm in (("A", "Exposure to automation"), ("D", "Declining demand"), ("G", "Skill gap to target role"), ("C", "Skill concentration in a narrow area"))
        ],
        "lowDemandSkills": low_demand,
        "formula": "R = 0.3·A + 0.25·D + 0.25·G + 0.2·C",
    }


def learning_links(skill):
    q = urllib.parse.quote_plus(skill)
    links = []
    r = SKILLS.get(skill, {}).get("resource")
    if r:
        links.append({"title": f"{skill}: recommended resource", "url": r})
    links.append({"title": f"Coursera courses: {skill}", "url": f"https://www.coursera.org/search?query={q}"})
    links.append({"title": f"YouTube tutorials: {skill}", "url": f"https://www.youtube.com/results?search_query={q}+tutorial"})
    return links


# ---------- AI call 1: resume extraction ----------
P1 = ("You are an expert career analyst. Extract structured professional information from the provided resume and "
      "self-description. Identify current and previous roles, years of experience, education, technical skills, soft "
      "skills, skill proficiency where supported by evidence, and professional responsibilities. Do not invent skills or "
      "experience. If proficiency is unclear, return \"unknown\". Return JSON exactly: {\"current_role\":str|null,"
      "\"previous_roles\":[str],\"years_experience\":number|null,\"education\":[str],\"technical_skills\":[{\"name\":str,"
      "\"canonical\":str|null,\"proficiency\":\"beginner\"|\"intermediate\"|\"advanced\"|\"unknown\",\"evidence\":str}],"
      "\"soft_skills\":[{\"name\":str,\"canonical\":str|null,\"evidence\":str}],\"responsibilities\":[str],"
      "\"preferences\":{\"location\":str|null,\"work_type\":str|null,\"salary\":str|null}}. "
      "\"canonical\" must be exactly one name from the allowed list when the skill matches one, else null. "
      "\"evidence\" is a short verbatim quote (max 15 words) from the text.")


def extract_profile(uid, text):
    out = llm_json(uid, P1, "Allowed canonical skills: " + json.dumps(SKILL_NAMES) + "\n\nTEXT:\n" + text[:14000], 1400)
    tech = []
    for s in out.get("technical_skills", []) or []:
        if isinstance(s, dict) and s.get("name"):
            tech.append({"name": str(s["name"])[:60], "canonical": canon(s.get("canonical")) or canon(s.get("name")),
                         "proficiency": s.get("proficiency") if s.get("proficiency") in ("beginner", "intermediate", "advanced") else "unknown",
                         "evidence": str(s.get("evidence", ""))[:160]})
    soft = [{"name": str(s["name"])[:60], "canonical": canon(s.get("canonical")) or canon(s.get("name")), "evidence": str(s.get("evidence", ""))[:160]}
            for s in (out.get("soft_skills") or []) if isinstance(s, dict) and s.get("name")]
    try:
        years = float(out.get("years_experience")) if out.get("years_experience") is not None else None
    except (TypeError, ValueError):
        years = None
    prefs = out.get("preferences") if isinstance(out.get("preferences"), dict) else {}
    return {"current_role": out.get("current_role"), "previous_roles": strs(out.get("previous_roles"), 6),
            "years_experience": years, "education": strs(out.get("education"), 5), "technical_skills": tech[:40],
            "soft_skills": soft[:15], "responsibilities": strs(out.get("responsibilities"), 8, 240),
            "preferences": {k: (str(prefs.get(k))[:100] if prefs.get(k) else None) for k in ("location", "work_type", "salary")}}


# ---------- AI call 2: risk & alternatives ----------
P2 = ("You are a labor market and career transition analyst. Analyze the supplied professional profile and the supplied "
      "labor market dataset (real US job postings). Identify the user's existing strengths, vulnerable skills, skill gaps, "
      "and three realistic alternative occupations chosen ONLY from the supplied role list. For each occupation, explain "
      "transferable skills, missing skills, and transition difficulty. Use only the supplied market data for factual market "
      "claims. Never invent salary statistics, job counts, or trends. Distinguish evidence from estimates. The risk score is "
      "already computed by a fixed formula — do not change it, only explain each factor in 1-2 sentences. Return JSON: "
      "{\"factor_explanations\":{\"A\":str,\"D\":str,\"G\":str,\"C\":str},\"strengths\":[str],"
      "\"growing_skills\":[{\"skill\":str,\"reason\":str}],\"stable_skills\":[{\"skill\":str,\"reason\":str}],"
      "\"declining_skills\":[{\"skill\":str,\"reason\":str}],\"alternatives\":[{\"role\":str,\"transferable_skills\":[str],"
      "\"missing_skills\":[str],\"transition_difficulty\":\"low\"|\"medium\"|\"high\",\"time_to_transition\":str,\"why\":str}],"
      "\"protection_plan\":[{\"period\":\"Days 1-30\"|\"Days 31-60\"|\"Days 61-90\",\"focus\":str,\"actions\":str,\"result\":str}]}. "
      "Growing skills = skills worth adding (prefer ones in high demand in the dataset); stable = user skills with steady "
      "demand; declining = user skills or tasks most exposed to automation/declining demand. 2-4 items each. English.")


def api_report(body, u):
    uid = u["id"]
    cv, about = (body.get("cvText") or "").strip()[:12000], (body.get("about") or "").strip()[:4000]
    cur, tgt = str(body.get("currentRole", "")), str(body.get("targetRole", ""))
    if len(cv) + len(about) < 40:
        raise ApiError(400, "Upload your CV or tell us about yourself (at least a few sentences).")
    if tgt not in ROLES:
        raise ApiError(400, "Please choose a target role.")
    if not JOBS["jobs"]:
        raise ApiError(503, "No job data yet. Run the scraper first.")
    text = (("CV:\n" + cv + "\n\n") if cv else "") + (("ABOUT MYSELF:\n" + about) if about else "")
    prof = extract_profile(uid, text)
    have = {s["canonical"] for s in prof["technical_skills"] + prof["soft_skills"] if s["canonical"]} | keyword_skills(text)
    risk = risk_score(have, cur, tgt)
    stats = {r: role_stats(r) for r in ROLES}
    roles_view = sorted([{"role": r, "match": match_pct(have, s), "vacancies": s["vacancies"], "salary": s["salary"],
                          "topSkills": [t["skill"] for t in s["topSkills"][:8]]} for r, s in stats.items()], key=lambda x: -x["match"])
    market = {"dataset": f"{len(JOBS['jobs'])} real US postings scraped {JOBS['meta'].get('scrapedAt', '')[:10]}",
              "roles": roles_view}
    ai = llm_json(uid, P2, json.dumps({
        "profile": prof, "user_canonical_skills": sorted(have), "current_role": cur, "target_role": tgt,
        "target_salary": body.get("targetSalary"), "risk": {"score": risk["score"], "factors": risk["factors"]},
        "role_list": list(ROLES), "market": market}, ensure_ascii=False), 3000)

    def skl(x):
        return [{"skill": str(i.get("skill", ""))[:60], "reason": str(i.get("reason", ""))[:220]} for i in (x or []) if isinstance(i, dict) and i.get("skill")][:4]

    alts, seen = [], set()
    for a in ai.get("alternatives", []) or []:
        r = a.get("role") if isinstance(a, dict) else None
        if r in ROLES and r not in seen and r != cur:
            seen.add(r)
            alts.append(a)
    for rv in roles_view:  # top up from data if the model returned fewer than 3 valid roles
        if len(alts) >= 3:
            break
        if rv["role"] not in seen and rv["role"] != cur:
            seen.add(rv["role"])
            alts.append({"role": rv["role"]})
    alternatives = []
    for a in alts[:3]:
        r, s = a["role"], stats[a["role"]]
        data_missing = [t["skill"] for t in s["topSkills"] if t["skill"] not in have][:6]
        alternatives.append({
            "role": r, "match": match_pct(have, s), "vacancies": s["vacancies"], "salary": s["salary"],
            "haveSkills": [t["skill"] for t in s["topSkills"] if t["skill"] in have],
            "missingSkills": data_missing,
            "transferable": strs(a.get("transferable_skills"), 6, 80), "aiMissing": strs(a.get("missing_skills"), 6, 80),
            "difficulty": a.get("transition_difficulty") if a.get("transition_difficulty") in ("low", "medium", "high") else "medium",
            "time": str(a.get("time_to_transition", "") or "3–6 months (estimate)")[:60], "why": str(a.get("why", ""))[:300],
            "courses": [l for sk in data_missing[:2] for l in learning_links(sk)[:1]],
        })
    fx = ai.get("factor_explanations") or {}
    for f in risk["factors"]:
        f["explanation"] = str(fx.get(f["key"], ""))[:300]
    plan = [{"period": str(p.get("period", ""))[:20], "focus": str(p.get("focus", ""))[:80], "actions": str(p.get("actions", ""))[:300],
             "result": str(p.get("result", ""))[:160]} for p in (ai.get("protection_plan") or []) if isinstance(p, dict)][:3]

    # vacancies: most relevant real postings, with the user's skill gaps per posting
    alt_roles = {a["role"] for a in alternatives}
    vac = []
    for j in JOBS["jobs"]:
        req = set(j.get("mandatory", [])) | set(j.get("preferred", []))
        missing = [s for s in j.get("mandatory", []) if s not in have] + [s for s in j.get("preferred", []) if s not in have]
        rel = (3 if j["role"] == tgt else 2 if j["role"] in alt_roles else 1 if j["role"] == cur else 0)
        if rel == 0:
            continue
        cov = len(req & have) / len(req) if req else 0
        vac.append({**{k: j.get(k) for k in ("id", "title", "company", "location", "remote", "url", "postedAt", "role", "level", "salary")},
                    "matched": sorted(req & have), "missing": missing[:8], "fit": round(100 * cov), "quotes": j.get("quotes", [])[:2],
                    "_rank": rel * 100 + cov * 50})
    vac.sort(key=lambda v: -v["_rank"])
    for v in vac:
        v.pop("_rank")
        v["salaryYear"] = annual(v["salary"])
    value = market_value(vac, tgt)

    report = {
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "currentRole": cur, "targetRole": tgt,
        "targetSalary": body.get("targetSalary"), "studyHours": body.get("studyHours"),
        "profile": prof, "skills": sorted(have), "risk": risk, "strengths": strs(ai.get("strengths"), 5),
        "growing": skl(ai.get("growing_skills")), "stable": skl(ai.get("stable_skills")), "declining": skl(ai.get("declining_skills")),
        "alternatives": alternatives, "protectionPlan": plan, "vacancies": vac[:40], "value": value,
        "dataset": {"count": len(JOBS["jobs"]), "scrapedAt": JOBS["meta"].get("scrapedAt"), "note": JOBS["meta"].get("note"),
                    "estimatesNote": TAX["note"]},
    }
    st = user_state(uid)
    if st.get("report"):  # archive the previous report as a PDF before replacing it
        archive_report(uid, st)
    st.update({"input": {k: body.get(k) for k in ("about", "currentRole", "targetRole", "targetSalary", "studyHours")},
               "report": report, "roadmap": None, "interview": None, "result": None})
    save_state(uid, st)
    append_log("events.jsonl", {"name": "report_generated", "uid": uid})
    return report


# ---------- AI call 3: roadmap ----------
P3 = ("You are a professional career transition coach. Based on the user's profile, selected target vacancies, and "
      "identified skill gaps, generate a practical 90-day career transition roadmap. Divide it into three 30-day phases. "
      "Include learning objectives, practical assignments, portfolio projects, and measurable outcomes. Prioritize skills "
      "that close the most important gaps. Make the plan realistic for the user's available study time. Return JSON: "
      "{\"target_role\":str,\"duration_days\":90,\"summary\":str,\"milestones\":[{\"period\":\"Days 1-30\",\"skills\":[str],"
      "\"objectives\":[str],\"assignments\":[str],\"deliverable\":str,\"measurable_outcome\":str,\"hours_per_week\":number}]}. "
      "Use skill names exactly as given in missing_skills when possible.")


def api_roadmap(body, u):
    st = user_state(u["id"])
    rep = st.get("report")
    if not rep:
        raise ApiError(400, "Generate your career report first.")
    ids = [str(i) for i in (body.get("jobIds") or [])][:3]
    jobs = [v for v in rep["vacancies"] if v["id"] in ids]
    if not jobs:
        raise ApiError(400, "Select 1 to 3 vacancies.")
    missing = []
    for j in jobs:
        for s in j["missing"]:
            if s not in missing:
                missing.append(s)
    roles = [j["role"] for j in jobs]
    target = max(set(roles), key=roles.count)
    ai = llm_json(u["id"], P3, json.dumps({
        "current_skills": rep["skills"], "current_role": rep["currentRole"], "target_role": target,
        "selected_vacancies": [{"title": j["title"], "company": j["company"], "missing_skills": j["missing"]} for j in jobs],
        "missing_skills": missing, "years_experience": rep["profile"].get("years_experience"),
        "study_time_per_week": rep.get("studyHours") or "3-6 hours"}, ensure_ascii=False), 3000)
    ms = []
    for i, m in enumerate((ai.get("milestones") or [])[:3]):
        if not isinstance(m, dict):
            continue
        skills = strs(m.get("skills"), 5, 60)
        ms.append({"period": str(m.get("period") or f"Days {i * 30 + 1}-{i * 30 + 30}")[:20], "skills": skills,
                   "objectives": strs(m.get("objectives"), 4, 200), "assignments": strs(m.get("assignments"), 4, 220),
                   "deliverable": str(m.get("deliverable", ""))[:200], "outcome": str(m.get("measurable_outcome", ""))[:220],
                   "hours": m.get("hours_per_week") if isinstance(m.get("hours_per_week"), (int, float)) else None,
                   "resources": [l for s in skills[:3] for l in learning_links(canon(s) or s)]})
    if len(ms) < 3:
        raise ApiError(502, "AI returned an incomplete roadmap. Please retry.")
    roadmap = {"targetRole": str(ai.get("target_role") or target)[:60], "durationDays": 90, "summary": str(ai.get("summary", ""))[:400],
               "milestones": ms, "vacancies": [{k: j[k] for k in ("id", "title", "company", "url", "missing")} for j in jobs],
               "missingSkills": missing}
    st.update({"roadmap": roadmap, "interview": None, "result": None})
    save_state(u["id"], st)
    return roadmap


# ---------- AI call 4: interview ----------
P4 = ("You create a short knowledge check for a learner, based on skills from their 90-day roadmap. Return JSON: "
      "{\"mcq\":[{\"skill\":str,\"question\":str,\"options\":[4 strings],\"answer_index\":0-3,\"explanation\":str}] (exactly 5, "
      "practical, unambiguous, one correct option, vary the correct index),\"open\":[{\"skill\":str,\"question\":str,"
      "\"expected_concepts\":[3-5 str]}] (exactly 2: one applied/technical scenario, one about explaining a decision to "
      "stakeholders)}. English. Level: intermediate.")


def api_questions(body, u):
    st = user_state(u["id"])
    rm = st.get("roadmap")
    if not rm:
        raise ApiError(400, "Generate your learning roadmap first.")
    skills = []
    for m in rm["milestones"]:
        for s in m["skills"]:
            if s not in skills:
                skills.append(s)
    ai = llm_json(u["id"], P4, json.dumps({"target_role": rm["targetRole"], "roadmap_skills": skills[:10]}), 3000)
    mcq = []
    for q in (ai.get("mcq") or [])[:5]:
        opts = strs(q.get("options"), 4, 200) if isinstance(q, dict) else []
        try:
            ai_idx = int(q.get("answer_index"))
        except (TypeError, ValueError):
            continue
        if len(opts) == 4 and 0 <= ai_idx < 4 and q.get("question"):
            mcq.append({"id": f"m{len(mcq) + 1}", "skill": str(q.get("skill", ""))[:60], "question": str(q["question"])[:400],
                        "options": opts, "answer": ai_idx, "explanation": str(q.get("explanation", ""))[:400]})
    opn = [{"id": f"o{i + 1}", "skill": str(q.get("skill", ""))[:60], "question": str(q.get("question", ""))[:500],
            "expected": strs(q.get("expected_concepts"), 5, 80)} for i, q in enumerate((ai.get("open") or [])[:2]) if isinstance(q, dict) and q.get("question")]
    if len(mcq) < 3 or len(opn) < 1:
        raise ApiError(502, "AI returned incomplete questions. Please retry.")
    st.update({"interview": {"mcq": mcq, "open": opn, "targetRole": rm["targetRole"]}, "result": None})
    save_state(u["id"], st)
    return public_interview(st["interview"])


def public_interview(iv):
    return {"mcq": [{k: q[k] for k in ("id", "skill", "question", "options")} for q in iv["mcq"]],
            "open": [{k: q[k] for k in ("id", "skill", "question")} for q in iv["open"]], "targetRole": iv["targetRole"]}


P5 = ("You give formative feedback on text interview answers using a fixed rubric. For EACH answer score each criterion "
      "0-4 (0 none, 2 partial, 4 strong; 1 and 3 intermediate): Technical correctness, Reasoning, Evidence / examples, "
      "Clarity. Judge ONLY what is in the answer; never assume missing content. Short or vague answers must get low scores "
      "and the feedback must say evidence is missing. Return JSON {\"evaluations\":[{\"id\":str,\"rubricScores\":[{\"criterion\":str,"
      "\"score\":int,\"explanation\":str}],\"strengths\":[str],\"weaknesses\":[str],\"citedAnswerSegments\":[verbatim short "
      "quotes from the answer],\"improvedStructure\":str}]}. This is learning feedback, not a hiring decision.")


def api_submit(body, u):
    st = user_state(u["id"])
    iv = st.get("interview")
    if not iv:
        raise ApiError(400, "Start the interview first.")
    picks = body.get("mcq") or {}
    answers = {str(a.get("id")): str(a.get("answer", "")).strip()[:4000] for a in (body.get("open") or []) if isinstance(a, dict)}
    if any(q["id"] not in picks for q in iv["mcq"]):
        raise ApiError(400, "Please answer all multiple-choice questions.")
    if any(not answers.get(q["id"]) for q in iv["open"]):
        raise ApiError(400, "Please answer the open questions before finishing.")
    mcq_res = [{"id": q["id"], "picked": picks[q["id"]], "answer": q["answer"], "correct": picks[q["id"]] == q["answer"],
                "explanation": q["explanation"]} for q in iv["mcq"]]
    ai = llm_json(u["id"], P5, json.dumps({"answers": [{"id": q["id"], "question": q["question"], "expected_concepts": q["expected"],
                                                         "answer": answers[q["id"]]} for q in iv["open"]]}, ensure_ascii=False), 3000)
    by_id = {str(e.get("id")): e for e in (ai.get("evaluations") or []) if isinstance(e, dict)}
    evals = []
    for q in iv["open"]:
        e, ans = by_id.get(q["id"], {}), answers[q["id"]]
        words, low = len(ans.split()), ans.lower()
        rs = {str(r.get("criterion", "")).lower(): r for r in (e.get("rubricScores") or []) if isinstance(r, dict)}
        scores = []
        for c in RUBRIC:
            r = rs.get(c.lower(), {})
            try:
                s = max(0, min(4, int(r.get("score", 0))))
            except (TypeError, ValueError):
                s = 0
            scores.append({"criterion": c, "score": min(s, 1) if words < 8 else s, "explanation": str(r.get("explanation", ""))[:300]})
        evals.append({"id": q["id"], "question": q["question"], "totalScore": round(sum(s["score"] for s in scores) / 16 * 100),
                      "rubricScores": scores, "strengths": strs(e.get("strengths"), 3, 250), "weaknesses": strs(e.get("weaknesses"), 3, 250),
                      "cited": [c for c in strs(e.get("citedAnswerSegments"), 3, 200) if c.lower().strip(' ".') in low],
                      "improvedStructure": str(e.get("improvedStructure", ""))[:700], "shortAnswer": words < 8})
    result = {"mcq": mcq_res, "mcqScore": sum(m["correct"] for m in mcq_res), "mcqTotal": len(mcq_res), "open": evals}
    st["result"] = result
    save_state(u["id"], st)
    append_log("events.jsonl", {"name": "interview_completed", "uid": u["id"]})
    return result


# ---------- auth ----------
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def api_signup(body, _):
    name, surname = str(body.get("name", "")).strip()[:60], str(body.get("surname", "")).strip()[:60]
    country, email = str(body.get("country", "")).strip()[:60], str(body.get("email", "")).strip().lower()[:120]
    pw = str(body.get("password", ""))
    if not (name and surname and country):
        raise ApiError(400, "Please fill in name, surname and country.")
    if not EMAIL_RE.match(email):
        raise ApiError(400, "Please enter a valid email (e.g. name@gmail.com).")
    if len(pw) < 8:
        raise ApiError(400, "Password must be at least 8 characters.")
    with _lock:
        users = read_json(USERS_F, {})
        if email in users:
            raise ApiError(409, "An account with this email already exists. Please log in.")
        salt = secrets.token_hex(16)
        u = {"id": secrets.token_hex(8), "name": name, "surname": surname, "country": country, "email": email,
             "salt": salt, "hash": hash_pw(pw, salt), "created": int(time.time())}
        users[email] = u
        write_json(USERS_F, users)
    return new_session(u)


def api_login(body, _):
    email, pw = str(body.get("email", "")).strip().lower(), str(body.get("password", ""))
    u = read_json(USERS_F, {}).get(email)
    if not u or not hmac.compare_digest(u["hash"], hash_pw(pw, u["salt"])):
        raise ApiError(401, "Wrong email or password.")
    return new_session(u)


def new_session(u):
    tok = secrets.token_urlsafe(32)
    with _lock:
        s = read_json(SESS_F, {})
        s[tok] = {"uid": u["id"], "email": u["email"], "exp": int(time.time()) + 7 * 86400}
        write_json(SESS_F, s)
    return {"user": public_user(u), "_cookie": tok}


def session_user(token):
    if not token:
        return None
    s = read_json(SESS_F, {}).get(token)
    if not s or s["exp"] < time.time():
        return None
    return read_json(USERS_F, {}).get(s["email"])


def api_logout(body, u, token=None):
    with _lock:
        s = read_json(SESS_F, {})
        s.pop(token, None)
        write_json(SESS_F, s)
    return {"ok": True, "_cookie": ""}


def api_me(u):
    st = user_state(u["id"])
    return {"user": public_user(u), "input": st.get("input"), "report": st.get("report"), "roadmap": st.get("roadmap"),
            "interview": public_interview(st["interview"]) if st.get("interview") else None, "result": st.get("result"),
            "feedbackDone": bool(st.get("feedbackDone")), "history": history_view(st)}


def append_log(name, record):
    record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(LOGS / name, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def api_event(body, u):
    name = str(body.get("name", ""))[:40]
    if not re.fullmatch(r"[a-z_]+", name):
        raise ApiError(400, "Bad event name.")
    append_log("events.jsonl", {"name": name, "uid": u["id"] if u else None})
    return {"ok": True}


def api_feedback(body, u):
    rating = body.get("helpfulRating")
    append_log("feedback.jsonl", {"uid": u["id"], "useful": rating if rating in (1, 2, 3, 4, 5) else None,
                                  "buyPro": str(body.get("buyPro", ""))[:10], "comment": str(body.get("comment", ""))[:1000]})
    st = user_state(u["id"])
    st["feedbackDone"] = True
    save_state(u["id"], st)
    return {"ok": True}


# ---------- market value (salary you deserve now) ----------
def annual(s):
    if not s or not s.get("min"):
        return None
    k = 2080 if s.get("period") == "hour" else 1
    return {"min": round(s["min"] * k), "max": round((s.get("max") or s["min"]) * k)}


def market_value(vac, target):
    """Salary range from real postings where the user already covers >= 50% of listed skills."""
    paid = [v for v in vac if v.get("salaryYear")]
    good = [v for v in paid if v["fit"] >= 50]
    basis = "postings where you match at least 50% of the listed skills"
    if len(good) < 3:
        good = sorted(paid, key=lambda v: -v["fit"])[:5]
        basis = "your 5 best-matching postings with a stated salary"
    tgt = [v for v in paid if v["role"] == target]
    res = {"basis": basis, "n": len(good), "readiness": round(statistics.mean(v["fit"] for v in vac if v["role"] == target))
           if any(v["role"] == target for v in vac) else None}
    if good:
        mids = [(v["salaryYear"]["min"] + v["salaryYear"]["max"]) / 2 for v in good]
        res.update({"min": min(v["salaryYear"]["min"] for v in good), "max": max(v["salaryYear"]["max"] for v in good),
                    "median": round(statistics.median(mids)),
                    "best": [{k: v[k] for k in ("id", "title", "company", "url", "salaryYear", "fit")}
                             for v in sorted(good, key=lambda v: -v["salaryYear"]["max"])[:3]]})
    if tgt:
        res["potential"] = {"role": target, "max": max(v["salaryYear"]["max"] for v in tgt),
                            "median": round(statistics.median((v["salaryYear"]["min"] + v["salaryYear"]["max"]) / 2 for v in tgt)), "n": len(tgt)}
    return res


# ---------- report history (PDF archive) ----------
def snapshot(rep):
    v = rep.get("value") or {}
    return {"createdAt": rep["createdAt"], "score": rep["risk"]["score"], "targetRole": rep["targetRole"],
            "valueMin": v.get("min"), "valueMax": v.get("max"), "readiness": v.get("readiness")}


def archive_report(uid, st):
    from report_pdf import render_report
    rep = st["report"]
    rid = re.sub(r"[^0-9]", "", rep["createdAt"])[:14] or str(int(time.time()))
    folder = USERDATA / uid
    folder.mkdir(exist_ok=True)
    u = next((x for x in read_json(USERS_F, {}).values() if x["id"] == uid), {})
    (folder / f"{rid}.pdf").write_bytes(render_report(rep, f"{u.get('name', '')} {u.get('surname', '')}".strip()))
    st.setdefault("history", []).insert(0, {"id": rid, **snapshot(rep)})


def history_view(st):
    cur = [snapshot(st["report"])] if st.get("report") else []
    return {"items": st.get("history", []), "progress": list(reversed(st.get("history", []))) + cur}


PUBLIC_POST = {"/api/signup": api_signup, "/api/login": api_login, "/api/event": api_event}
AUTH_POST = {"/api/report": api_report, "/api/roadmap": api_roadmap, "/api/interview/questions": api_questions,
             "/api/interview/submit": api_submit, "/api/feedback": api_feedback, "/api/logout": api_logout}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(PUBLIC), **kw)

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {fmt % args}")

    def token(self):
        c = SimpleCookie(self.headers.get("Cookie", ""))
        return c["tirek_sid"].value if "tirek_sid" in c else None

    def end_headers(self):  # CORS for a separately hosted frontend (Vercel) when not using the /api rewrite
        origin = (self.headers.get("Origin") or "").rstrip("/")
        if origin and origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Vary", "Origin")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def send_json(self, status, payload):
        cookie = payload.pop("_cookie", None) if isinstance(payload, dict) else None
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if cookie is not None:
            age = 7 * 86400 if cookie else 0
            self.send_header("Set-Cookie", f"tirek_sid={cookie}; Path=/; HttpOnly; {COOKIE_ATTRS}; Max-Age={age}")
        self.end_headers()
        self.wfile.write(data)

    def send_pdf(self, data, name):
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path.startswith("/api/history/") or path == "/api/report.pdf":
            u = session_user(self.token())
            if not u:
                return self.send_json(401, {"error": "Not logged in."})
            st = user_state(u["id"])
            if path == "/api/report.pdf":
                if not st.get("report"):
                    return self.send_json(404, {"error": "No report yet."})
                from report_pdf import render_report
                return self.send_pdf(render_report(st["report"], f"{u['name']} {u['surname']}"), "tirek-report-current.pdf")
            rid = path.rsplit("/", 1)[-1].removesuffix(".pdf")
            f = USERDATA / u["id"] / f"{rid}.pdf"
            if not re.fullmatch(r"\d{8,14}", rid) or not f.exists():
                return self.send_json(404, {"error": "Report not found."})
            return self.send_pdf(f.read_bytes(), f"tirek-report-{rid}.pdf")
        if path.startswith("/api/"):
            pass
        elif not PUBLIC.exists():
            return self.send_json(404, {"error": "Frontend is hosted separately."})
        if path == "/api/health":
            return self.send_json(200, {"ok": True, "ai": bool(OPENAI_KEY), "model": OPENAI_MODEL, "jobs": len(JOBS["jobs"])})
        if path == "/api/me":
            u = session_user(self.token())
            return self.send_json(200, api_me(u)) if u else self.send_json(401, {"error": "Not logged in."})
        if path == "/api/roles":
            return self.send_json(200, {"roles": list(ROLES), "jobs": len(JOBS["jobs"])})
        return super().do_GET()

    def do_POST(self):
        path = self.path.split("?")[0]
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n > MAX_BODY:
                raise ApiError(413, "Request is too large.")
            body = json.loads(self.rfile.read(n) or b"{}")
            tok = self.token()
            if path in PUBLIC_POST:
                return self.send_json(200, PUBLIC_POST[path](body, session_user(tok)))
            if path in AUTH_POST:
                u = session_user(tok)
                if not u:
                    raise ApiError(401, "Please log in again.")
                fn = AUTH_POST[path]
                return self.send_json(200, fn(body, u, tok) if fn is api_logout else fn(body, u))
            self.send_json(404, {"error": "Not found"})
        except ApiError as e:
            self.send_json(e.status, {"error": e.message})
        except json.JSONDecodeError:
            self.send_json(400, {"error": "Invalid JSON."})
        except Exception as e:
            print("Unhandled error:", type(e).__name__, e)
            self.send_json(500, {"error": "Unexpected server error. Please retry."})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"tirek → http://localhost:{port}  (AI {'ON, model ' + OPENAI_MODEL if OPENAI_KEY else 'OFF: add OPENAI_API_KEY to .env'}; {len(JOBS['jobs'])} jobs)")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
