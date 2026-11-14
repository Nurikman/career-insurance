# US job scraper

Builds `data/jobs_us.json` with 100 real, currently open US job postings, spread across the 12 target roles in `data/taxonomy.json`.

## Run

```bash
cd prototype1
python3 scraper/scrape_us_jobs.py            # options: --target 100 --delay 0.4
```

It needs `requests` and `beautifulsoup4`. A full run makes about 110 polite requests with a 0.4 s delay between them and takes a few minutes.

## Sources

The scraper reads public job-board APIs that employers publish for this purpose. None of them need authentication.

- **Greenhouse:** `https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true`, for about 50 US tech and media companies (Airbnb, Stripe, Databricks, Figma, Robinhood, Coinbase, Reddit, Datadog, Okta, Brex, NYT, Vox Media and others). The token list is `GREENHOUSE_BOARDS` in the script.
- **Lever:** `https://api.lever.co/v0/postings/{company}?mode=json`, for Palantir, Spotify, Zoox, Outreach, Hive and Ro (`LEVER_BOARDS`).

If a token returns nothing or an error, the scraper skips it.

## Pipeline

1. **US filter:** keeps a posting only if its location names a US city, a state or state code, "United States", or "Remote - US". Mixed lists such as "US; Toronto" are kept.
2. **Role:** keyword rules on the title assign exactly one of the 12 roles. Titles that match no role, and excluded titles such as sales, recruiting or engineering manager, are dropped.
3. **Skills:** matches taxonomy canonical names and aliases on word boundaries.
   - "R" and "Go" match only in clear programming context.
   - Each description is split into requirement, preferred and ignored sections (benefits, EEO, about-us). A skill found in a requirement section goes to `mandatory`. A skill found only in a preferred section, or on a line marked "a plus" or "preferred", goes to `preferred`.
   - Each job keeps up to 2 verbatim quotes of 140 characters or fewer.
4. **Salary:** taken only when the posting states it. Sources are Lever's `salaryRange` or an explicit `$X – $Y` range in the text. The period is `year` or `hour`. Otherwise the value is `null`.
5. **Level:** set from title keywords to Intern, Junior, Mid, Senior, Lead or Unspecified.
6. **Selection:** removes duplicates by URL and by company plus title, then picks jobs round-robin with about 8 per role and at most 10 per company. It prefers titles that fit the role closely, individual-contributor titles, and postings with a salary.

Full descriptions are not stored. Postings can close at any time, so re-run the scraper to refresh the data.
