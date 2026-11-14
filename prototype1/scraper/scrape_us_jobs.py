#!/usr/bin/env python3
"""
Scrape ~100 real, currently-open US job postings from public employer job-board
APIs (Greenhouse + Lever), classify them into the 12 target roles, extract
skills against data/taxonomy.json, and write data/jobs_us.json.

Run:
    python3 scraper/scrape_us_jobs.py            # from prototype1/
Options:
    --target N   number of jobs to output (default 100)
    --delay S    delay between HTTP requests in seconds (default 0.4)
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
TAXONOMY_PATH = ROOT / "data" / "taxonomy.json"
OUT_PATH = ROOT / "data" / "jobs_us.json"

HEADERS = {"User-Agent": "Mozilla/5.0 (career-advice-prototype; hackathon research)"}

# Public board tokens verified to respond (others are skipped gracefully).
GREENHOUSE_BOARDS = [
    "airbnb", "stripe", "databricks", "figma", "robinhood", "discord", "coinbase",
    "dropbox", "reddit", "instacart", "lyft", "pinterest", "duolingo", "gitlab",
    "cloudflare", "datadog", "affirm", "asana", "squarespace", "twilio", "mongodb",
    "elastic", "okta", "brex", "gusto", "chime", "samsara", "toast", "scaleai",
    "vercel", "sofi", "betterment", "carta", "flexport", "checkr", "gemini",
    "ripple", "oscar", "peloton", "roblox", "twitch", "voxmedia", "buzzfeed",
    "axios", "thenewyorktimes", "zscaler", "mercury", "attentive", "klaviyo", "block",
    "doordashusa",
]
LEVER_BOARDS = ["palantir", "spotify", "zoox", "outreach", "hive", "ro"]

LEVER_NAMES = {"palantir": "Palantir", "spotify": "Spotify", "zoox": "Zoox",
               "outreach": "Outreach", "hive": "Hive", "ro": "Ro"}

ROLES = ["AI Engineer", "Data Analyst", "Data Scientist", "Product Manager",
         "Software Engineer", "UX Designer", "Content Creator", "Marketing Manager",
         "Cybersecurity Analyst", "DevOps Engineer", "Business Analyst",
         "Financial Analyst"]

COMPANY_CAP = 10

# Clean display names where the board's own name is noisy.
COMPANY_NAMES = {"gusto": "Gusto", "doordashusa": "DoorDash", "chime": "Chime", "buzzfeed": "BuzzFeed",
                 "voxmedia": "Vox Media", "ripple": "Ripple", "oscar": "Oscar Health", "scaleai": "Scale AI",
                 "thenewyorktimes": "The New York Times", "block": "Block", "sofi": "SoFi"}

# ---------------------------------------------------------------- HTTP
_session = requests.Session()
_session.headers.update(HEADERS)


def fetch_json(url: str, delay: float, retries: int = 2):
    for attempt in range(retries + 1):
        try:
            r = _session.get(url, timeout=40)
            time.sleep(delay)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            if attempt == retries:
                print(f"  ! {url}: {e}", file=sys.stderr)
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


# ---------------------------------------------------------------- US location
US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
    "virginia": "VA", "washington": "WA", "west virginia": "WV", "wisconsin": "WI",
    "wyoming": "WY", "district of columbia": "DC",
}
STATE_CODES = set(US_STATES.values())
US_CITIES = [
    "san francisco", "new york", "nyc", "seattle", "los angeles", "austin", "boston",
    "chicago", "denver", "atlanta", "miami", "washington, d.c", "washington dc",
    "palo alto", "mountain view", "menlo park", "sunnyvale", "san jose", "san mateo",
    "redwood city", "oakland", "bellevue", "portland", "salt lake city", "san diego",
    "philadelphia", "pittsburgh", "dallas", "houston", "phoenix", "raleigh", "nashville",
    "minneapolis", "detroit", "columbus", "brooklyn", "foster city", "south san francisco",
    "irvine", "santa monica", "kirkland", "boulder", "ann arbor", "lehi", "charlotte",
]
NON_US = re.compile(
    r"\b(canada|toronto|vancouver|montreal|ontario|united kingdom|uk|london|ireland|dublin|"
    r"germany|berlin|munich|france|paris|spain|madrid|barcelona|netherlands|amsterdam|"
    r"india|bangalore|bengaluru|hyderabad|pune|mumbai|singapore|japan|tokyo|australia|"
    r"sydney|melbourne|brazil|sao paulo|mexico city|poland|warsaw|israel|tel aviv|"
    r"emea|apac|latam|europe|china|korea|seoul|sweden|stockholm|denmark|switzerland|"
    r"zurich|portugal|lisbon|argentina|colombia|costa rica|philippines|estonia)\b",
    re.I,
)
US_EXPLICIT = re.compile(
    r"\b(united states|u\.s\.a?\.?|usa|us|us-remote|remote[\s\-–,(]*us|us[\s\-–,(]*remote|"
    r"americas?\s*-\s*us)\b",
    re.I,
)


def is_us_location(loc: str) -> bool:
    if not loc:
        return False
    low = loc.lower()
    us_hit = bool(US_EXPLICIT.search(loc))
    if not us_hit:
        us_hit = any(c in low for c in US_CITIES) or any(
            re.search(rf"\b{s}\b", low) for s in US_STATES if s != "washington"
        )
    if not us_hit:
        # ", CA" style state codes
        for m in re.finditer(r",\s*([A-Z]{2})\b", loc):
            if m.group(1) in STATE_CODES:
                us_hit = True
                break
    if not us_hit:
        return False
    # Pure non-US list that happens to mention e.g. "Remote" - reject if non-US and
    # no explicit US marker / city at all. Mixed lists (US + other) are kept.
    if NON_US.search(loc) and not (US_EXPLICIT.search(loc) or any(c in low for c in US_CITIES)
                                   or re.search(r",\s*(%s)\b" % "|".join(STATE_CODES), loc)):
        return False
    return True


# ---------------------------------------------------------------- role / level
def _rx(*pats):
    return re.compile("|".join(pats), re.I)


ROLE_RULES = [  # order matters: first match wins
    ("Product Manager", _rx(r"product manager", r"product management", r"head of product", r"product owner",
                            r"director,? product\b")),
    ("Cybersecurity Analyst", _rx(r"\bsecurity (engineer|analyst|architect|specialist|operations|researcher)",
                                  r"\b(cyber ?security|infosec|detection (and|&) response|threat (intel|detection|hunt)",
                                  r"\bsoc analyst|offensive security|application security|appsec|product security)",
                                  r"\b(engineer|analyst)[^,]*,?\s*(security|detection)\b")),
    ("AI Engineer", _rx(r"machine learning engineer", r"\bml engineer", r"\bai engineer", r"applied ai",
                        r"\bai/ml\b", r"\bml/ai\b", r"\bllm\b", r"\bgenai\b", r"generative ai",
                        r"machine learning (infrastructure|platform)", r"engineer,? (machine learning|ml|ai)\b",
                        r"\bai (research|software) engineer", r"research engineer", r"engineer\W+(machine learning|ml|ai)\b")),
    ("Data Scientist", _rx(r"data scien", r"applied scientist", r"research scientist", r"quantitative (analyst|researcher)",
                           r"machine learning scientist", r"decision scien")),
    ("Financial Analyst", _rx(r"fp&a", r"financial (analyst|planning)", r"finance (analyst|associate)",
                              r"strategic finance", r"\bcorporate finance", r"treasury analyst",
                              r"revenue analyst", r"accounting analyst", r"investment analyst", r"finance manager")),
    ("Business Analyst", _rx(r"business (analyst|systems analyst|operations analyst|intelligence analyst|operations associate)",
                             r"\bbizops\b", r"business operations", r"strategy (and|&) operations (analyst|associate)",
                             r"operations analyst", r"systems analyst", r"business systems")),
    ("Data Analyst", _rx(r"data analyst", r"analytics (analyst|engineer|manager|lead)", r"product analyst",
                         r"insights analyst", r"marketing analyst", r"\banalyst,? (data|analytics)",
                         r"bi analyst", r"reporting analyst", r"data analytics")),
    ("UX Designer", _rx(r"product designer", r"\bux\b", r"\bui\b", r"user experience", r"interaction designer",
                        r"user research", r"ux research", r"design(er)?,? (systems|product)", r"content designer", r"visual designer",
                        r"brand designer", r"staff designer", r"senior designer")),
    ("Content Creator", _rx(r"\bcontent (creator|producer|strateg|marketing|writer|designer|manager|lead|editor)",
                            r"video (producer|editor)", r"social media", r"\bcreator\b", r"copywriter",
                            r"\bwriter\b", r"\beditor\b", r"producer", r"\breporter\b", r"\bjournalist\b",
                            r"editorial", r"podcast")),
    ("Marketing Manager", _rx(r"marketing (manager|lead|director|specialist)", r"product marketing",
                              r"growth marketing", r"brand marketing", r"demand gen", r"lifecycle marketing",
                              r"performance marketing", r"field marketing", r"partner marketing",
                              r"marketing,? ", r"\bmarketing\b")),
    ("DevOps Engineer", _rx(r"\bsre\b", r"site reliability", r"devops", r"dev ops", r"infrastructure engineer",
                            r"platform engineer", r"cloud engineer", r"engineer,? (infrastructure|platform|cloud|reliability|devops)",
                            r"production engineer", r"build (and|&) release", r"release engineer")),
    ("Product Manager", _rx(r"product lead")),
    ("Software Engineer", _rx(r"software engineer", r"software developer", r"(backend|back-end|frontend|front-end|full[- ]?stack) (engineer|developer)",
                              r"(ios|android|mobile|web) (engineer|developer)", r"\bswe\b",
                              r"software development engineer", r"engineer,? (backend|frontend|full[- ]?stack|product|web|mobile|ios|android)")),
]

# Titles to drop before classification (non-target or ambiguous)
DROP_TITLE = _rx(r"recruit", r"\bsales\b", r"account (executive|manager)", r"engineering manager",
                 r"manager,? (software )?engineering", r"director,? engineering", r"\bvp\b",
                 r"vice president", r"customer success", r"\blegal\b", r"counsel", r"paralegal",
                 r"support (engineer|specialist)", r"solutions? (engineer|architect)", r"talent",
                 r"\bhr\b", r"people partner", r"facilities", r"payroll", r"tax\b", r"hardware",
                 r"mechanical", r"electrical", r"firmware", r"technician", r"\bdriver\b")


NON_ENG_ROLES = {"UX Designer", "Content Creator", "Marketing Manager", "Business Analyst", "Financial Analyst",
                 "Product Manager", "Data Analyst"}
ENG_WORD = re.compile(r"\b(engineer|engineering|developer)\b", re.I)

# Titles that are a "core" fit for a role are preferred during selection.
CORE_FIT = {
    "AI Engineer": _rx(r"machine learning engineer", r"\bml engineer", r"\bai engineer", r"applied ai"),
    "Data Analyst": _rx(r"\banalyst\b"),
    "Data Scientist": _rx(r"data scientist"),
    "Product Manager": _rx(r"product manager"),
    "Software Engineer": _rx(r"software engineer", r"(backend|frontend|full[- ]?stack|ios|android) engineer"),
    "UX Designer": _rx(r"designer", r"researcher"),
    "Content Creator": _rx(r"content", r"video", r"social", r"creator", r"writer", r"editor", r"producer"),
    "Marketing Manager": _rx(r"marketing manager", r"manager,? .*marketing"),
    "Cybersecurity Analyst": _rx(r"security (analyst|engineer)"),
    "DevOps Engineer": _rx(r"\bsre\b", r"site reliability", r"devops", r"platform engineer", r"infrastructure engineer",
                           r"cloud engineer"),
    "Business Analyst": _rx(r"\banalyst\b"),
    "Financial Analyst": _rx(r"\banalyst\b", r"fp&a"),
}
SENIOR_MGMT = _rx(r"director", r"head of", r"\bvp\b", r"^manager,", r"sr\.? manager", r"senior manager",
                  r"tech lead manager", r"principal")


def classify_role(title: str) -> str | None:
    if DROP_TITLE.search(title):
        return None
    for role, rx in ROLE_RULES:
        if role in NON_ENG_ROLES and ENG_WORD.search(title) and role != "Product Manager":
            continue
        if role == "Data Analyst" and ENG_WORD.search(title) and not re.search(r"analytics engineer", title, re.I):
            continue
        if rx.search(title):
            return role
    return None


def detect_level(title: str) -> str:
    t = title.lower()
    if re.search(r"\bintern(ship)?\b|\bco-?op\b|apprentice", t):
        return "Intern"
    if re.search(r"\b(junior|jr\.?|entry[- ]level|new grad|graduate|associate)\b|\b(i|1)\b(?!\w)", t):
        return "Junior"
    if re.search(r"\b(lead|principal|staff|head of|director|manager,|architect)\b", t):
        return "Lead"
    if re.search(r"\b(senior|sr\.?|iii|iv)\b", t):
        return "Senior"
    if re.search(r"\b(mid|ii|2)\b", t):
        return "Mid"
    return "Unspecified"


# ---------------------------------------------------------------- salary
SAL_RX = re.compile(
    r"\$\s?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*([kK])?\s*(?:USD)?\s*(?:[-–—]|to)\s*"
    r"(?:USD\s*)?\$?\s?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*([kK])?\s*(USD)?"
    r"(?:\s*(?:per|/|an|a)\s*(hour|hr|year|yr|annum|annually))?",
)


def _num(s: str, k: str | None) -> float:
    v = float(s.replace(",", ""))
    return v * 1000 if k else v


def parse_salary(text: str) -> dict | None:
    for m in SAL_RX.finditer(text):
        lo = _num(m.group(1), m.group(2))
        hi = _num(m.group(3), m.group(4) or m.group(2))
        if lo <= 0 or hi < lo:
            continue
        ctx = text[max(0, m.start() - 80): m.end() + 40].lower()
        unit = (m.group(6) or "").lower()
        hourly = unit in ("hour", "hr") or (hi < 500 and re.search(r"hour|hourly|/hr", ctx))
        if hourly and hi < 500:
            period = "hour"
        elif hi >= 20000:
            period = "year"
        else:
            continue  # not a salary (e.g. "$5-10M" funding text)
        return {"min": int(round(lo)), "max": int(round(hi)), "currency": "USD",
                "period": period, "text": re.sub(r"\s+", " ", m.group(0)).strip()[:120]}
    return None


# ---------------------------------------------------------------- skills
def build_skill_patterns(taxonomy: dict):
    pats = []
    for name, info in taxonomy["skills"].items():
        if name == "R":
            rx = re.compile(r"(?:\bR programming\b|\brstudio\b|\btidyverse\b|\bggplot2?\b|"
                            r"(?:Python|SQL|Julia|SAS|Stata),\s*(?:or\s+|and\s+)?R\b(?![&\-'])|"
                            r"\bR\s*(?:,|/|or|and)\s*(?:Python|SQL)\b|\bin R\b(?![&\-']))")
            pats.append((name, rx))
            continue
        if name == "Go":
            rx = re.compile(r"(?:\bgolang\b|\bGo\s*\(golang\)|"
                            r"(?:Python|Java|Rust|C\+\+|Ruby|Scala|Kotlin|TypeScript),\s*(?:or\s+|and\s+)?Go\b|"
                            r"\bGo\s*(?:,|/|or|and)\s*(?:Python|Java|Rust|C\+\+|Ruby|Scala|Kotlin)\b)", re.I if False else 0)
            pats.append((name, rx))
            continue
        terms = [name] + list(info.get("aliases", []))
        alts = []
        for t in terms:
            e = re.escape(t)
            if t.lower() == "soc":
                alts.append(r"\bSOC\b(?!\s*[12]\b|\s*2)")
                continue
            if t.lower() in ("rag", "sem", "iac", "elt", "s3", "ec2", "dax", "pmp", "dcf", "ppc", "ga4", "k8s"):
                alts.append(rf"(?<![\w-]){re.escape(t.upper()) if t.lower() != 'k8s' else 'k8s'}(?![\w-])")
                continue
            alts.append(rf"(?<![\w-]){e}(?![\w-])" if t[-1].isalnum() else rf"(?<![\w-]){e}")
        flags = 0 if name in ("SQL",) else re.I
        # case-sensitive alternatives (uppercase acronyms) handled inline via (?-i:)
        rx_parts = []
        for a, t in zip(alts, terms):
            if t.lower() in ("rag", "sem", "iac", "elt", "s3", "ec2", "dax", "pmp", "dcf", "ppc", "soc"):
                rx_parts.append(f"(?-i:{a})")
            else:
                rx_parts.append(a)
        pats.append((name, re.compile("|".join(rx_parts), re.I)))
    return pats


IGNORE_HEAD = _rx(r"^about (us|the company|[A-Z]\w+$)", r"benefit", r"perks", r"compensation", r"pay (range|transparency)",
                  r"salary", r"equal opportunity", r"\beeo\b", r"our (mission|values|culture|commitment)",
                  r"why (join|work)", r"who we are", r"life at", r"what we offer", r"accommodation",
                  r"privacy", r"location", r"hybrid", r"in-?office")
PREF_HEAD = _rx(r"nice to have", r"nice-to-have", r"preferred", r"bonus", r"plus\b", r"pluses", r"desired",
                r"ideal(ly)?", r"extra credit", r"stand out", r"even better", r"great to have", r"good to have")
REQ_HEAD = _rx(r"requirement", r"qualification", r"what you('|’)?ll need", r"you (have|bring|are|might be)",
               r"about you", r"who you are", r"must have", r"skills", r"experience", r"what we('|’)?re looking for",
               r"what you bring", r"what we look for", r"you('|’)?ll need", r"minimum", r"basic qualifications",
               r"responsibilit", r"what you('|’)?ll do", r"the role", r"in this role", r"day to day", r"you will")


def html_to_lines(raw_html: str) -> list[str]:
    soup = BeautifulSoup(html.unescape(raw_html or ""), "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text("\n")
    return [re.sub(r"\s+", " ", ln).strip() for ln in text.split("\n") if ln.strip()]


def section_lines(lines: list[str]) -> list[tuple[str, str]]:
    """Tag each line with section: req | pref | ignore | unk."""
    out, cur, saw_head = [], "unk", False
    for ln in lines:
        is_head = len(ln) <= 70 and (ln.endswith(":") or not re.search(r"[.;]$", ln)) and len(ln.split()) <= 9
        if is_head:
            if PREF_HEAD.search(ln):
                cur, saw_head = "pref", True
                continue
            if IGNORE_HEAD.search(ln) and not REQ_HEAD.search(ln):
                cur = "ignore"
                continue
            if REQ_HEAD.search(ln):
                cur, saw_head = "req", True
                continue
        sec = cur
        if sec in ("req", "unk") and re.search(r"\b(is a plus|a plus|preferred|nice to have|bonus points?|is a bonus)\b", ln, re.I):
            sec = "pref"
        out.append((sec, ln))
    return out


def extract_skills(lines: list[str], patterns, company: str = "") -> tuple[list[str], list[str], list[dict]]:
    tagged = section_lines(lines)
    req_hits: dict[str, tuple[str, re.Match]] = {}
    pref_hits: dict[str, tuple[str, re.Match]] = {}
    for sec, ln in tagged:
        if sec == "ignore":
            continue
        for name, rx in patterns:
            m = next((mm for mm in rx.finditer(ln)
                      if not company or mm.group(0).lower() not in company.lower()), None)
            if not m:  # ignore matches that are just the employer's name (e.g. "Databricks")
                continue
            if sec == "pref":
                pref_hits.setdefault(name, (ln, m))
            else:
                req_hits.setdefault(name, (ln, m))
    mandatory = list(req_hits)
    preferred = [s for s in pref_hits if s not in req_hits]
    quotes, used = [], set()
    # Prefer quotes from requirement lines with technical (non-soft) skills
    soft = {"Communication", "Stakeholder communication", "Leadership", "Agile", "Project management"}
    ordered = sorted(req_hits.items(), key=lambda kv: (kv[0] in soft, len(kv[1][0])))
    for name, (ln, m) in ordered + list(pref_hits.items()):
        if len(quotes) >= 2:
            break
        if ln in used:
            continue
        quotes.append({"skill": name, "text": _clip(ln, m.start(), m.end())})
        used.add(ln)
    return mandatory, preferred, quotes


def _clip(line: str, s: int, e: int, limit: int = 140) -> str:
    line = line.strip()
    if len(line) <= limit:
        return line
    start = max(0, s - (limit - (e - s)) // 2)
    end = min(len(line), start + limit)
    start = max(0, end - limit)
    seg = line[start:end]
    # trim partial words at the edges (keeps it a verbatim substring)
    if start > 0 and " " in seg:
        seg = seg[seg.index(" ") + 1:]
    if end < len(line) and " " in seg:
        seg = seg[: seg.rindex(" ")]
    return seg.strip()


# ---------------------------------------------------------------- sources
def scrape_greenhouse(token: str, delay: float) -> tuple[list[dict], str | None]:
    meta = fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{token}", delay)
    company = COMPANY_NAMES.get(token) or (meta or {}).get("name", "").strip() or token.title()
    data = fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true", delay)
    if not data:
        return [], None
    raw = []
    for j in data.get("jobs", []):
        loc = (j.get("location") or {}).get("name") or ""
        offices = ", ".join(o.get("name", "") for o in j.get("offices") or [])
        if not is_us_location(loc) and not (loc.strip().lower() in ("remote", "") and is_us_location(offices)):
            continue
        url = re.sub(r"^http://", "https://", j.get("absolute_url") or "")
        if not url.startswith("http"):
            continue
        raw.append({
            "id": f"gh-{token}-{j['id']}", "title": j.get("title", "").strip(), "company": company,
            "location": (f"{loc} ({offices})" if loc and not is_us_location(loc) else loc) or offices, "url": url,
            "postedAt": j.get("first_published") or j.get("updated_at"),
            "_lines": html_to_lines(j.get("content", "")), "source": "greenhouse", "_src": f"greenhouse:{token}",
        })
    return raw, company


def scrape_lever(token: str, delay: float) -> tuple[list[dict], str | None]:
    data = fetch_json(f"https://api.lever.co/v0/postings/{token}?mode=json", delay)
    if not data:
        return [], None
    company = LEVER_NAMES.get(token, token.title())
    raw = []
    for p in data:
        cats = p.get("categories") or {}
        loc = cats.get("location") or ""
        all_locs = ", ".join(cats.get("allLocations") or [])
        country = (p.get("country") or "").upper()
        if not (is_us_location(loc) or (country == "US" and not NON_US.search(loc))):
            continue
        lines = [ln.strip() for ln in (p.get("descriptionPlain") or "").split("\n") if ln.strip()]
        for lst in p.get("lists") or []:
            lines.append(lst.get("text", "").strip() + ":")
            lines.extend(html_to_lines(lst.get("content", "")))
        add = [ln.strip() for ln in (p.get("additionalPlain") or "").split("\n") if ln.strip()]
        sr = p.get("salaryRange") or None
        salary = None
        if sr and sr.get("min") and sr.get("max") and (sr.get("currency") or "USD") == "USD":
            interval = (sr.get("interval") or "").lower()
            period = "hour" if "hour" in interval else "year"
            salary = {"min": int(sr["min"]), "max": int(sr["max"]), "currency": "USD", "period": period,
                      "text": f"${int(sr['min']):,} - ${int(sr['max']):,} {sr.get('interval') or ''}".strip()}
        created = p.get("createdAt")
        raw.append({
            "id": f"lv-{token}-{p['id']}", "title": (p.get("text") or "").strip(), "company": company,
            "location": loc or all_locs, "url": p.get("hostedUrl") or "",
            "postedAt": datetime.fromtimestamp(created / 1000, timezone.utc).isoformat() if created else None,
            "_lines": lines, "_extra": add, "_salary": salary,
            "_remote": (p.get("workplaceType") or "").lower() == "remote",
            "source": "lever", "_src": f"lever:{token}",
        })
    return raw, company


# ---------------------------------------------------------------- selection
def select_balanced(cands_by_role: dict[str, list[dict]], target: int) -> list[dict]:
    chosen, chosen_ids = [], set()
    company_count: Counter = Counter()
    role_count: Counter = Counter()
    role_companies: dict[str, Counter] = defaultdict(Counter)

    def pick(role: str) -> bool:
        pool = [c for c in cands_by_role.get(role, []) if c["id"] not in chosen_ids
                and company_count[c["company"]] < COMPANY_CAP]
        if not pool:
            return False
        pool.sort(key=lambda c: (not CORE_FIT[role].search(c["title"]), bool(SENIOR_MGMT.search(c["title"])),
                                 role_companies[role][c["company"]], company_count[c["company"]],
                                 c["salary"] is None, -len(c["mandatory"]) - len(c["preferred"])))
        c = pool[0]
        chosen.append(c)
        chosen_ids.add(c["id"])
        company_count[c["company"]] += 1
        role_count[role] += 1
        role_companies[role][c["company"]] += 1
        return True

    base = target // len(ROLES)  # 8
    for quota in range(1, base + 1):
        for role in ROLES:
            if role_count[role] < quota and len(chosen) < target:
                pick(role)
    # fill remaining from roles with surplus, round-robin, fewest-first
    while len(chosen) < target:
        progressed = False
        for role in sorted(ROLES, key=lambda r: role_count[r]):
            if len(chosen) >= target:
                break
            if pick(role):
                progressed = True
                break
        if not progressed:
            break
    return chosen


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=100)
    ap.add_argument("--delay", type=float, default=0.4)
    args = ap.parse_args()

    taxonomy = json.loads(TAXONOMY_PATH.read_text())
    patterns = build_skill_patterns(taxonomy)

    raw_all: list[dict] = []
    for token in GREENHOUSE_BOARDS:
        jobs, company = scrape_greenhouse(token, args.delay)
        print(f"greenhouse:{token:16s} US jobs: {len(jobs)}")
        raw_all.extend(jobs)
    for token in LEVER_BOARDS:
        jobs, company = scrape_lever(token, args.delay)
        print(f"lever:{token:21s} US jobs: {len(jobs)}")
        raw_all.extend(jobs)

    # dedup by URL and by (company, title)
    seen_url, seen_ct, cands_by_role = set(), set(), defaultdict(list)
    for r in raw_all:
        key_ct = (r["company"].lower(), r["title"].lower())
        if r["url"] in seen_url or key_ct in seen_ct:
            continue
        role = classify_role(r["title"])
        if not role:
            continue
        seen_url.add(r["url"])
        seen_ct.add(key_ct)
        lines = r["_lines"]
        mandatory, preferred, quotes = extract_skills(lines, patterns, r["company"])
        salary = r.get("_salary") or parse_salary("\n".join(lines + r.get("_extra", [])))
        loc = r["location"]
        cands_by_role[role].append({
            "id": r["id"], "title": r["title"], "company": r["company"], "location": loc,
            "remote": bool(r.get("_remote")) or bool(re.search(r"remote", loc, re.I)),
            "url": r["url"], "postedAt": r["postedAt"], "role": role, "level": detect_level(r["title"]),
            "salary": salary, "mandatory": mandatory, "preferred": preferred, "quotes": quotes,
            "source": r["source"], "_src": r["_src"],
        })

    print("\nCandidates per role:", {r: len(cands_by_role[r]) for r in ROLES})
    chosen = select_balanced(cands_by_role, args.target)
    chosen.sort(key=lambda j: (ROLES.index(j["role"]), j["company"], j["title"]))
    sources = sorted({j.pop("_src") for j in chosen})

    out = {
        "meta": {
            "scrapedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "count": len(chosen),
            "sources": sources,
            "note": "Real public postings scraped from employer job boards; may close at any time.",
        },
        "jobs": chosen,
    }
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"\nWrote {len(chosen)} jobs -> {OUT_PATH} ({OUT_PATH.stat().st_size // 1024} KB)")
    print("Per role:", dict(Counter(j["role"] for j in chosen)))
    print("With salary:", sum(1 for j in chosen if j["salary"]))
    print("Companies:", dict(Counter(j["company"] for j in chosen)))


if __name__ == "__main__":
    main()
