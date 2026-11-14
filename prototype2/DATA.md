# Data & privacy design

One SQLite database: `DATA_DIR/tirek.db` (Railway volume in production). Schema and rules live in [`backend/db.py`](backend/db.py).

## What is stored

| Table | Contents | Why | Kept |
|---|---|---|---|
| `users` | name, surname, country, email, PBKDF2 password hash, consent flags + version | account, login | until the user deletes the account |
| `sessions` | SHA-256 hash of the login token, expiry | stay logged in | 7 days |
| `consent_log` | every consent given / withdrawn, with version and time | proof of consent | with the account |
| `profiles` | current/target role, target salary, study time | prefill the profile | with the account |
| `profiles.cv_text`, `about`, `cv_name` | raw CV text and "About you" | reuse a CV | **only with opt-in `consent_store_cv`**; deleted after `CV_RETENTION_DAYS` (90) or immediately when consent is withdrawn |
| `reports` | each generated report (extracted skills/experience, risk, salary range, vacancies) | history, progress, PDFs | with the account |
| `state` | current roadmap and interview | app state | with the account |
| `feedback` | rating, "would buy Pro", comment | product validation | kept; becomes anonymous (`user_id = NULL`) when the account is deleted |
| `events` | anonymous funnel events (`signup`, `report_generated`, …) | product metrics | same as feedback |
| `admin_audit` | every admin request, including denied attempts | accountability | permanent |

Not stored: passwords in plain text, session tokens in plain text, CV files (PDFs are read in the browser), CV text without consent.

## Consent (sign-up)
1. **Required:** Terms & Privacy Policy (`/#/privacy`).
2. **Optional:** keep my CV text for reuse (90 days).
3. **Optional:** use my anonymised results to improve tirek.

Users can change 2 and 3 any time in **Profile → Your data**. Withdrawing 2 erases the stored CV at once.

## User rights (Profile → Your data)
- **Download my data:** `GET /api/me/export` returns a JSON file with everything linked to the account.
- **Delete my account:** `POST /api/me/delete` with the password. This hard-deletes the account, sessions, consents, profile, CV, reports and state. Feedback and events are kept only without the user link.

## Viewing logs as the team (`/admin.html`)
- Turned on only when the server has `ADMIN_TOKEN` set (24+ random characters, e.g. `python3 -c "import secrets;print(secrets.token_urlsafe(32))"`). Never commit it.
- **Overview:** users, reports, average usefulness, "would buy Pro", funnel, countries, consent counts.
- **Feedback:** comments with country and a short pseudonymous user ref. No names or emails.
- **Users:** a masked list (`A. N.`, `a***@gmail.com`). Opening a user shows full contact details, goal, reports, and CV text **only if that user consented**. Each opening is written to the access log.
- **Access log:** who looked at what and when, including failed attempts.

Good practice: open individual users only for support or quality checks, never export personal data to other tools, rotate `ADMIN_TOKEN` if it leaks, and use only anonymous data (overview, feedback) for analysis and pitch decks.
