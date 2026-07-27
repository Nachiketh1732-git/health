# Wellness baseline

A personal health analytics dashboard that compares each day's readings to
**your own** 30-day range rather than to a population average.

FastAPI + Postgres + React. Deploys to Render from GitHub with one Blueprint
file. No Docker, no CLI, no credit card.

---

## Deploy

### 1. Get a database that will outlive the project

Render's free Postgres is **deleted 30 days after creation**, with no warning
and no migration path. If this is going on your CV, use [Neon](https://neon.tech)
instead — permanent free tier, same Postgres, two minutes to set up.

Sign up, create a project, copy the connection string. It looks like:

```
postgresql://user:password@ep-something.aws.neon.tech/neondb?sslmode=require
```

### 2. Push to GitHub

```bash
git init
git add .
git commit -m "Wellness baseline platform"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/wellness-baseline.git
git push -u origin main
```

### 3. Deploy the Blueprint

On [render.com](https://render.com): **New → Blueprint → connect your repo.**
Render reads `render.yaml` and creates both services. It will prompt you for:

| Variable | What to enter |
|---|---|
| `DATABASE_URL` | Your Neon connection string |
| `GEMINI_API_KEY` | Optional — free key from [aistudio.google.com](https://aistudio.google.com). Blank is fine; insights fall back to generated text |
| `ALLOWED_ORIGINS` | Leave blank |

`JWT_SECRET` is generated automatically. First build takes about five minutes.

### 4. Fill it with data

```bash
python backend/seed.py \
  --api https://wellness-api-XXXX.onrender.com \
  --email you@example.com --password something-long-enough
```

Sign in at your `wellness-web` URL with those credentials.

---

## Run it locally

No database needed — it falls back to a SQLite file.

```bash
# terminal 1
cd backend
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000

# terminal 2
cd frontend
npm install && npm run dev          # http://localhost:5173

# terminal 3
python backend/seed.py --email you@example.com --password local-dev-password
```

Tests: `cd backend && pytest -q` (19 tests, no database required).

---

## What lives where

```
render.yaml            Blueprint — both services and their wiring
.github/workflows/     CI: pytest + frontend build on every push

backend/
  app/analytics.py     baselines, reference bands, readiness, pattern rules
  app/narrative.py     Gemini wrapper with a rules-based fallback
  app/security.py      bcrypt + JWT
  app/models.py        User, Reading — consent lives on the user row
  app/routers/         auth.py, data.py
  tests/               API behaviour + scoring regressions
  seed.py              60 days of synthetic data with a planted anomaly

frontend/
  src/components/ReferenceBand.jsx   the signature UI element
  src/lib/api.js                     includes the cold-start wake-up ping
```

---

## Decisions worth defending

These are the parts an interviewer will actually probe.

**Personal baseline, not population norm.** A resting heart rate of 62 means
nothing on its own. The same 62 for someone who normally sits at 54 is worth
noticing. Every metric is a z-score against that user's own 30-day window, and
the UI borrows the reference-range band from a lab report because people
already know how to read one.

**The scoring formula has a deadband, and that was a bug fix.** The first
version summed deviations across seven metrics. Since roughly half of them land
on their adverse side by chance on any given day, a completely ordinary day
scored 31 out of 100. Deviations under 0.75 SD now cost nothing, and each metric
is capped at 3.5 SD so correlated pairs — resting HR and HRV almost always move
together — can't double-count one physiological event. `test_scoring.py` pins
the behaviour across 60 simulated users per scenario.

**The model phrases, the rules decide.** Gemini never sees raw readings and
never does arithmetic. `analytics.py` computes what is true; the model only
turns it into a sentence. The numbers stay deterministic, token cost stays near
zero, and an API outage degrades to plain text rather than to wrong numbers.

**Consent is a gate, not a checkbox.** `POST /api/readings` returns 403 unless
`store_metrics` is on. The insight endpoint skips the model entirely unless
`generate_insights` is on. Both are checked per request against the user row, so
revoking takes effect on the next call rather than the next login. Delete is a
hard delete with a cascade — no tombstone, no soft-delete flag.

**The frontend is a static site, deliberately.** Render static sites are free,
CDN-served, and never sleep. Only the API cold-starts, so the app renders
instantly and shows an honest "waking the server" state instead of looking
broken for 40 seconds.

**Partial writes don't clobber.** A manual check-in with only `energy` filled in
updates that one column and leaves everything else alone, so a wearable import
earlier the same day survives. That's the `created`/`updated` split in the
ingest response.

---

## Known gaps

Worth naming before someone finds them.

- **No wearable integration.** `seed.py` generates synthetic data. Wiring the
  Google Fit or Fitbit REST API is roughly a day's work and is the obvious
  next thing to build.
- **`create_all` instead of migrations.** Fine at this size. The moment you
  need to change a column on data you care about, add Alembic.
- **Free-tier cold start.** 30–60 seconds after 15 minutes idle. Handled in
  the UI, not eliminated. Render's paid tier or an uptime pinger fixes it.
- **Sessions live in `sessionStorage`.** Simple and XSS-exposed like any token
  in JS-reachable storage. httpOnly cookies would be the hardening step.

---

**This is a wellness tracker, not a medical device.** It describes how your own
readings compare to your own history. It does not diagnose, treat, or rule out
any condition.
