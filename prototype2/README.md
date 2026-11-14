# tirek — Career Insurance · prototype 2

**Goal:** career insurance for professionals — see your market value, your career risk, and the exact skills that raise both.

What's new vs prototype 1:
- Minimal flat design: blue / yellow / green / white, rounded color blocks, light + dark mode, less text (details are collapsible)
- **Market value now**: min–max salary from real US postings you already match (≥ 50% of listed skills), median, best-paid matches, potential in the target role, and per-vacancy salaries
- **Readiness** for the target role + **progress** chart across report versions
- **History**: every new report archives the previous one as a PDF (`/api/history/<id>.pdf`); the current report downloads at `/api/report.pdf`
- About section with picture blocks on the landing page
- SQLite database with consent, CV retention, data export / account deletion and an audited admin view (see [DATA.md](DATA.md))
- Split for deployment: `frontend/` → Vercel, `backend/` → Railway (see [DEPLOY.md](DEPLOY.md))

## Run locally
```
cd backend
cp .env.example .env    # add OPENAI_API_KEY
python3 server.py       # http://localhost:8000 (serves ../frontend too)
```
No dependencies (Python 3.9+ standard library). Refresh real vacancies: `pip install -r scraper/requirements.txt && python3 scraper/scrape_us_jobs.py`.

## Structure
```
frontend/   index.html, styles.css, app.js, map.js, admin.html, admin.js, config.js, vercel.json
backend/    server.py (API), db.py (SQLite + privacy rules), report_pdf.py (PDF writer), data/ (jobs + taxonomy), scraper/, railway.json, Procfile
```
