"""Career Insurance (tirek) prototype server.

Zero dependencies: Python 3.9+ standard library only.
Run:  python3 server.py   ->  http://localhost:8000
Put your OpenAI key into .env (OPENAI_API_KEY=...).
"""
import json
import os
import re
import ssl
import time
import uuid
import urllib.error
import urllib.request
from collections import defaultdict
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
DATA = ROOT / "data"
LOGS = DATA / "logs"
LOGS.mkdir(parents=True, exist_ok=True)


# ---------- .env ----------
def load_env():
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
LLM_CALLS_PER_HOUR = int(os.environ.get("LLM_CALLS_PER_HOUR", "60"))
MAX_BODY = 1_000_000  # 1 MB request cap (CV text, answers)

JOBS = json.loads((DATA / "jobs.json").read_text(encoding="utf-8"))
TAXONOMY = sorted({r["skill"] for j in JOBS["jobs"] for r in j["mandatory"] + j["preferred"]} | set(JOBS["extraSkills"]))
RUBRIC = ["Technical correctness", "Reasoning", "Evidence / examples", "Clarity"]


def ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    if Path("/etc/ssl/cert.pem").exists():  # macOS python.org builds ship without certs
        return ssl.create_default_context(cafile="/etc/ssl/cert.pem")
    return ssl.create_default_context()


SSL_CTX = ssl_context()
_calls = defaultdict(list)


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


# ---------- LLM ----------
def llm_json(ip, system, user, max_tokens=900):
    if not OPENAI_KEY:
        raise ApiError(503, "AI is not configured: add OPENAI_API_KEY to prototype1/.env and restart the server.")
    now = time.time()
    _calls[ip] = [t for t in _calls[ip] if now - t < 3600]
    if len(_calls[ip]) >= LLM_CALLS_PER_HOUR:
        raise ApiError(429, "AI usage limit reached for this hour. Please try again later.")
    _calls[ip].append(now)

    body = {
        "model": OPENAI_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    for attempt in range(2):
        req = urllib.request.Request(
            OPENAI_URL,
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=45, context=SSL_CTX) as r:
                data = json.loads(r.read())
            text = data["choices"][0]["message"]["content"]
            return json.loads(text)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="ignore")[:400]
            # Some newer models reject temperature / max_tokens: retry once without them.
            if e.code == 400 and attempt == 0 and ("temperature" in detail or "max_tokens" in detail):
                body.pop("temperature", None)
                if "max_tokens" in detail:
                    body["max_completion_tokens"] = body.pop("max_tokens", max_tokens)
                continue
            if e.code == 401:
                raise ApiError(502, "OpenAI rejected the API key. Check OPENAI_API_KEY in .env.")
            raise ApiError(502, f"AI service error ({e.code}). Please retry.")
        except (urllib.error.URLError, TimeoutError):
            raise ApiError(504, "AI service is unreachable or timed out. Please retry.")
        except (KeyError, json.JSONDecodeError):
            raise ApiError(502, "AI returned an invalid response. Please retry.")
    raise ApiError(502, "AI request failed. Please retry.")


# ---------- skills ----------
def keyword_skills(text):
    low = " " + text.lower() + " "
    found = []
    for skill, aliases in JOBS["aliases"].items():
        names = aliases if skill == "R" else [skill] + aliases  # bare "R" matches initials
        for a in names:
            m = re.search(r"(?<![a-z0-9])" + re.escape(a.lower()) + r"(?![a-z0-9])", low)
            if m:
                s = max(0, m.start() - 40)
                found.append({"name": skill, "evidence": text[s:m.end() + 40].strip()})
                break
    return found


def api_profile(body, ip):
    cv = (body.get("cvText") or "").strip()
    if len(cv) < 30:
        raise ApiError(400, "CV text is too short. Paste your CV or use a sample profile.")
    cv = cv[:12000]
    try:
        out = llm_json(
            ip,
            "You extract skills from a CV for a career tool. Return JSON {\"skills\":[{\"name\":str,\"evidence\":str}]}. "
            "name MUST be one of the allowed skills exactly as written. evidence MUST be a short verbatim quote "
            "(max 15 words) copied from the CV. Only include skills with explicit evidence. Never invent.",
            "Allowed skills: " + json.dumps(TAXONOMY) + "\n\nCV:\n" + cv,
            600,
        )
        skills, seen = [], set()
        for s in out.get("skills", []):
            name = str(s.get("name", ""))
            ev = str(s.get("evidence", ""))[:160]
            if name in TAXONOMY and name not in seen:
                seen.add(name)
                verified = ev and ev.lower()[:40] in cv.lower()
                skills.append({"name": name, "evidence": ev if verified else "", "confirmed": False})
        return {"skills": skills, "method": "ai"}
    except ApiError as e:
        # Deterministic fallback: keyword matching (honest, labelled as such)
        skills = [dict(s, confirmed=False) for s in keyword_skills(cv)]
        return {"skills": skills, "method": "keywords", "notice": e.message + " Used keyword matching instead."}


# ---------- interview ----------
def api_questions(body, ip):
    gap = str(body.get("targetSkill", ""))[:60]
    role = str(body.get("targetRole", "Senior Data Analyst"))[:60]
    skills = [str(s)[:40] for s in body.get("skills", [])][:30]
    if not gap:
        raise ApiError(400, "Target skill is missing. Generate your career report first.")
    out = llm_json(
        ip,
        "You are a fair interviewer for a career-growth tool. Return JSON {\"questions\":[q1,q2]} where each q is "
        "{\"id\":\"q1\"|\"q2\",\"targetSkill\":str,\"questionType\":\"technical\"|\"behavioral\",\"questionText\":str,"
        "\"expectedConcepts\":[3-5 short strings]}. q1: one technical/situational question testing the target skill at "
        "the target seniority, answerable in 4-8 sentences of text. q2: one behavioral question on communication or "
        "decision-making connected to the same skill. English. No multi-part questions.",
        f"Target role: {role}\nTarget skill (top gap): {gap}\nCandidate confirmed skills: {', '.join(skills)}",
        600,
    )
    qs = out.get("questions", [])
    if len(qs) < 2 or not all(q.get("questionText") for q in qs[:2]):
        raise ApiError(502, "AI returned incomplete questions. Please retry.")
    res = []
    for i, q in enumerate(qs[:2]):
        res.append({
            "id": f"q{i + 1}",
            "targetSkill": gap,
            "questionType": "technical" if i == 0 else "behavioral",
            "questionText": str(q["questionText"])[:600],
            "expectedConcepts": [str(c)[:80] for c in q.get("expectedConcepts", [])][:5],
            "rubricCriteria": RUBRIC,
        })
    return {"questions": res}


def api_evaluate(body, ip):
    q = body.get("question") or {}
    answer = (body.get("answer") or "").strip()[:5000]
    if not answer:
        raise ApiError(400, "Please write an answer before submitting.")
    words = len(answer.split())
    out = llm_json(
        ip,
        "You give formative feedback on a text interview answer using a fixed rubric. Score each criterion 0-4 "
        "(0 none, 2 partial, 4 strong; 1 and 3 intermediate): Technical correctness, Reasoning, Evidence / examples, "
        "Clarity. Judge ONLY what is in the answer; never assume missing content. Short or vague answers must get "
        "low scores and the feedback must say evidence is missing. Return JSON {\"rubricScores\":[{\"criterion\":str,"
        "\"score\":int,\"explanation\":str}],\"strengths\":[str],\"weaknesses\":[str],\"citedAnswerSegments\":[verbatim "
        "short quotes from the answer],\"improvedStructure\":str (a short outline of a stronger answer),"
        "\"recommendedPractice\":{\"title\":str,\"minutes\":int 20-40,\"steps\":[3 short str],\"successCriterion\":str}}. "
        "This is learning feedback, not a hiring decision.",
        f"Question ({q.get('questionType', '')}, skill: {q.get('targetSkill', '')}): {q.get('questionText', '')}\n"
        f"Expected concepts: {', '.join(q.get('expectedConcepts', []))}\n\nCandidate answer:\n{answer}",
        900,
    )
    by_name = {str(r.get("criterion", "")).lower(): r for r in out.get("rubricScores", [])}
    scores = []
    for c in RUBRIC:
        r = by_name.get(c.lower(), {})
        try:
            s = max(0, min(4, int(r.get("score", 0))))
        except (TypeError, ValueError):
            s = 0
        if words < 8:
            s = min(s, 1)  # guard: very short answers cannot score high
        scores.append({"criterion": c, "score": s, "explanation": str(r.get("explanation", ""))[:400]})
    low = answer.lower()
    cited = [str(x)[:200] for x in out.get("citedAnswerSegments", []) if str(x).strip() and str(x).lower().strip(' ".') in low]
    p = out.get("recommendedPractice") or {}
    return {
        "questionId": q.get("id"),
        "totalScore": round(sum(s["score"] for s in scores) / 16 * 100),
        "rubricScores": scores,
        "strengths": [str(x)[:300] for x in out.get("strengths", [])][:4],
        "weaknesses": [str(x)[:300] for x in out.get("weaknesses", [])][:4],
        "citedAnswerSegments": cited[:4],
        "improvedStructure": str(out.get("improvedStructure", ""))[:900],
        "recommendedPractice": {
            "title": str(p.get("title", ""))[:160],
            "minutes": max(20, min(40, int(p.get("minutes", 30) or 30))) if str(p.get("minutes", "30")).isdigit() else 30,
            "steps": [str(x)[:200] for x in p.get("steps", [])][:3],
            "successCriterion": str(p.get("successCriterion", ""))[:300],
        },
        "shortAnswer": words < 8,
    }


def append_log(name, record):
    record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(LOGS / name, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def api_event(body, ip):
    name = str(body.get("name", ""))[:40]
    if not re.fullmatch(r"[a-z_]+", name):
        raise ApiError(400, "Bad event name.")
    append_log("events.jsonl", {"name": name, "sid": str(body.get("sid", ""))[:40]})
    return {"ok": True}


def api_feedback(body, ip):
    rec = {
        "anonymousSessionId": str(body.get("sid", ""))[:40],
        "completedReport": bool(body.get("completedReport")),
        "interviewFinished": bool(body.get("interviewFinished")),
        "helpfulRating": body.get("helpfulRating") if body.get("helpfulRating") in (1, 2, 3, 4, 5) else None,
        "nextUpdateInterest": bool(body.get("nextUpdateInterest")),
        "pricingInterest": str(body.get("pricingInterest", ""))[:20],
        "comment": str(body.get("comment", ""))[:1000],
    }
    append_log("feedback.jsonl", rec)
    return {"ok": True}


def api_stats():
    counts = defaultdict(int)
    f = LOGS / "events.jsonl"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                counts[json.loads(line)["name"]] += 1
            except Exception:
                pass
    return dict(counts)


POST_ROUTES = {
    "/api/profile": api_profile,
    "/api/interview/questions": api_questions,
    "/api/interview/evaluate": api_evaluate,
    "/api/event": api_event,
    "/api/feedback": api_feedback,
}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(PUBLIC), **kw)

    def log_message(self, fmt, *args):  # keep logs free of request bodies / PII
        print(f"{self.address_string()} {fmt % args}")

    def send_json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/jobs":
            return self.send_json(200, JOBS)
        if path == "/api/health":
            return self.send_json(200, {"ok": True, "ai": bool(OPENAI_KEY), "model": OPENAI_MODEL})
        if path == "/api/stats":
            return self.send_json(200, api_stats())
        return super().do_GET()

    def do_POST(self):
        path = self.path.split("?")[0]
        fn = POST_ROUTES.get(path)
        if not fn:
            return self.send_json(404, {"error": "Not found"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n > MAX_BODY:
                raise ApiError(413, "Request is too large.")
            body = json.loads(self.rfile.read(n) or b"{}")
            self.send_json(200, fn(body, self.client_address[0]))
        except ApiError as e:
            self.send_json(e.status, {"error": e.message})
        except json.JSONDecodeError:
            self.send_json(400, {"error": "Invalid JSON."})
        except Exception as e:  # never leak internals
            print("Unhandled error:", type(e).__name__, e)
            self.send_json(500, {"error": "Unexpected server error. Please retry."})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"Career Insurance prototype → http://localhost:{port}  (AI {'ON, model ' + OPENAI_MODEL if OPENAI_KEY else 'OFF: add OPENAI_API_KEY to .env'})")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
