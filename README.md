# tirek — Career Insurance

**Career insurance for professionals: see your market value, your career risk, and the exact skills that raise both.**

➡️ **Current version: [prototype 2](prototype2/)** · [deploy guide](prototype2/DEPLOY.md)

- **Market value now** — min / max / median salary from real US postings you already match
- **Career risk score** — fixed formula `R = 0.3A + 0.25D + 0.25G + 0.2C`
- **Readiness & progress** — tracked across every CV update; previous reports saved as PDFs
- **Real vacancies** — 100 US postings with salaries and your skill gaps
- **90-day roadmap + AI interview** — learning links, quiz and rubric feedback

## Run
```
cd prototype2/backend
cp .env.example .env      # add OPENAI_API_KEY
python3 server.py         # http://localhost:8000
```
Python 3.9+ only, no dependencies. Deploy: frontend → Vercel, backend → Railway ([DEPLOY.md](prototype2/DEPLOY.md)).

## Repository
| Folder | Status |
|---|---|
| [`prototype2/`](prototype2/) | **Current** — minimal design, market value, PDF history, Vercel + Railway split |
| [`prototype1/`](prototype1/) | Previous version, kept for reference |
