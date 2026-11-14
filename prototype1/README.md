# tirek — Career Insurance (prototype 1)

Data Analyst → Senior Data Analyst (New York): profile → career report → 2-question AI interview with rubric → growth plan → feedback.
The **Main** tab is a live-style world map of vacancies fitting your career (simulated data).

## Run
1. Put your key in `.env`: `OPENAI_API_KEY=sk-...` (optional: `OPENAI_MODEL`, default `gpt-4o-mini`).
2. `python3 server.py` → open http://localhost:8000

No dependencies (Python 3.9+ standard library). On Railway, `PORT` is read from the environment and the key can be set as a service variable instead of `.env`.

## API
- `GET /api/jobs` – labelled sample job snapshot (`data/jobs.json`)
- `POST /api/profile` – CV text → suggested skills with quotes (AI, keyword fallback)
- `POST /api/interview/questions` – 2 questions for the top gap
- `POST /api/interview/evaluate` – rubric JSON (4 criteria × 0–4), validated server-side
- `POST /api/event`, `POST /api/feedback`, `GET /api/stats` – anonymous metrics in `data/logs/`

## Honesty notes
- `data/jobs.json` uses **fictional employers** modelled on typical postings; replace it with a real, dated snapshot (Greenhouse/Ashby) before claiming real data. Links open a real job search for the same role/city.
- Map data is simulated. Interview scores are formative feedback, not hiring decisions.
- CVs are not stored; `.env` and logs are git-ignored.
