# Deploy: Vercel (frontend) + Railway (backend)

```
Browser ──► Vercel (static frontend)
              │  /api/*  rewrite (same origin → cookies just work, no CORS)
              ▼
            Railway (python3 server.py) ──► OpenAI API
              │
              └─ Volume /data  (users, sessions, reports, PDFs)
```

## 1. Backend on Railway
1. New Project → Deploy from GitHub repo → set **Root Directory** to `prototype2/backend`.
   Railway detects Python from `requirements.txt` and starts `python3 server.py` (`railway.json`, health check `/api/health`). `PORT` is provided by Railway.
2. Add a **Volume** mounted at `/data`.
3. Variables:
   | Name | Value |
   |---|---|
   | `OPENAI_API_KEY` | your key |
   | `OPENAI_MODEL` | e.g. `gpt-4o-mini` (optional) |
   | `DATA_DIR` | `/data` |
4. Settings → Networking → **Generate Domain**, e.g. `https://tirek-api.up.railway.app`. Check `https://…/api/health`.

## 2. Frontend on Vercel
1. Add New Project → same repo → **Root Directory** `prototype2/frontend`, Framework preset **Other**, no build command.
2. Edit `frontend/vercel.json` and replace `YOUR-BACKEND.up.railway.app` with your Railway domain. Commit.
3. Deploy. The site calls `/api/*` on its own domain; Vercel forwards it to Railway, so the login cookie stays first-party.

## Alternative: call Railway directly (no rewrite)
- `frontend/config.js`: `window.API_BASE = 'https://tirek-api.up.railway.app'`
- Railway variables: `ALLOWED_ORIGINS=https://your-app.vercel.app` and `CROSS_SITE_COOKIES=1`
- Note: some browsers block third-party cookies, so the rewrite above is more reliable.

## Notes
- Without a volume, Railway's filesystem resets on each deploy (accounts and PDFs would be lost).
- The job dataset ships with the backend (`backend/data/jobs_us.json`). Re-run the scraper locally and redeploy to refresh it.
- Never commit `.env`; set secrets in Railway variables.
