# tirek — Career Insurance (prototype 1)

Landing (live vacancy map) → Sign up / Log in → **Profile** (CV + about yourself + goal) → **Career report** (Career Risk Score, skill trends, alternative roles, 90-day protection plan, real US vacancies) → **Learning roadmap** (choose up to 3 vacancies → 90-day plan with learning links) → **AI interview** (5 MCQ + 2 open questions with rubric) → **Feedback** (usefulness + would you buy Pro).

## Run
1. Put your key in `.env`: `OPENAI_API_KEY=sk-...` (optional `OPENAI_MODEL`, default `gpt-4o-mini`).
2. `python3 server.py` → open http://localhost:8000

No dependencies for the app (Python 3.9+ standard library). `PORT` is read from the environment (Railway).

## Real vacancies
`data/jobs_us.json` holds ~100 real US postings scraped from public employer job boards. Refresh with:
```
pip install requests beautifulsoup4
python3 scraper/scrape_us_jobs.py
```
(restart the server afterwards). See `scraper/README.md`.

## AI calls (OpenAI, JSON mode)
1. `/api/report` → resume extraction (Prompt 1) + risk & alternatives analysis (Prompt 2)
2. `/api/roadmap` → 90-day roadmap for the selected vacancies (Prompt 3); learning links come from a curated list + Coursera/YouTube searches, never from the model
3. `/api/interview/questions` → MCQ + open questions from roadmap skills; answer key stays on the server
4. `/api/interview/submit` → MCQ graded on the server, open answers scored on a fixed 4×0–4 rubric

## Career Risk Score (fixed backend formula, not the LLM)
`R = 0.3·A + 0.25·D + 0.25·G + 0.2·C`, score = 100·R
- **A** automation exposure of the current role (illustrative estimate table in `data/taxonomy.json`)
- **D** declining demand = 0.5 × role demand-trend estimate + 0.5 × share of your skills found in < 3% of scraped postings
- **G** skill gap = 1 − share of the target role's most-requested skills (in the scraped postings) you have
- **C** concentration = 1 − (distinct non-soft skill domains − 1) / 4
Weights are demonstrational and must be calibrated on data for a real product.

## Data & privacy
Users/sessions are stored in `data/users.json`, `data/sessions.json`, per-user results in `data/userdata/` (passwords hashed with PBKDF2). CV text is read in the browser and sent only to generate the report; it is not saved. All of these plus `.env` are git-ignored. The landing map uses simulated data.
