# Wellness baseline

A personal health analytics dashboard that compares each day's readings to
**your own** 30-day range rather than to a population average. Runs entirely on
Google Cloud managed services.

---

## Run it locally in two minutes

No Google Cloud account needed. With `GOOGLE_CLOUD_PROJECT` unset the backend
uses an in-memory store and stubs out auth.

```bash
# terminal 1
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8080

# terminal 2
cd frontend
npm install
npm run dev            # http://localhost:5173

# terminal 3 — fill it with 60 days of synthetic data
python seed/generate.py --api http://localhost:8080
```

Then reload the dashboard. The seeder plants a deliberate anomaly in the last
few days so the signal detection has something to catch.

---

## Deploy to Google Cloud

You need a GCP project with billing enabled and `gcloud` installed.

```bash
gcloud auth login
./deploy/deploy.sh your-project-id
```

That script enables the APIs, creates Artifact Registry and Firestore, makes a
least-privilege service account, builds both containers, deploys them to Cloud
Run, and pins the API's CORS to the deployed web origin. It is idempotent — run
it again to redeploy.

**One manual step afterwards.** In the Firebase console for the same project:
Authentication → Sign-in method → enable Google, then add your Cloud Run web
domain under Authorized domains. Copy the web API key and auth domain into
`VITE_FIREBASE_API_KEY` / `VITE_FIREBASE_AUTH_DOMAIN` and re-run the script so
they get baked into the bundle.

### What it costs

At personal-project traffic this sits inside the free tier. Cloud Run scales to
zero, Firestore's free quota is 50k reads a day, and the Gemini call fires once
per dashboard load. Expect roughly ₹0–200/month unless you leave min-instances
above zero.

---

## Layout

```
backend/
  main.py        FastAPI routes, Firebase token verification, consent gate
  analytics.py   baselines, reference bands, readiness score, pattern rules
  narrative.py   Vertex AI wrapper with a rules-based fallback
  store.py       Firestore, with an in-memory fallback for local dev
frontend/
  src/components/ReferenceBand.jsx   the signature UI element
  src/lib/api.js, firebase.js
deploy/
  deploy.sh, cloudbuild-web.yaml
seed/
  generate.py    synthetic wearable data
```

---

## Decisions worth defending

These are the parts an interviewer will actually probe.

**Personal baseline, not population norm.** A resting heart rate of 62 means
nothing on its own. The same 62 for someone who normally sits at 54 is worth
noticing. Every band is a z-score against that user's own 30-day window, and
the UI borrows the reference-range band from a lab report because people
already know how to read it.

**The model phrases, the rules decide.** Gemini never sees raw readings and
never does arithmetic. `analytics.py` computes what is true; the model only
turns that into a sentence. This makes the numbers deterministic, keeps token
cost near zero, and means a Vertex outage degrades to plain text rather than to
wrong numbers.

**Consent is a gate, not a checkbox.** `POST /api/readings` returns 403 unless
`store_metrics` is on, and the insight endpoint skips Vertex entirely unless
`generate_insights` is on. Revoking consent stops the behaviour immediately
because it is checked per request, not at signup. Delete is a hard delete — no
tombstone, no soft-delete flag.

**Two thresholds, both conservative.** 1.5 SD gets a quiet "worth watching";
2.5 SD gets a flag. A wellness app that cries wolf gets uninstalled, and the
cost of a false alarm about your own heart is higher than the cost of a missed
nudge. The multipliers in `readiness()` are the main tuning knob if the scores
feel too harsh.

**It says what it is not.** The disclaimer is in the product, not buried in
terms. The narrative prompt forbids naming conditions, suggesting treatments,
or telling anyone to eat less or train harder — it can only describe what
changed and suggest mentioning it to a clinician. That boundary is the reason
this can ship at all.

---

## Where to take it next

- Google Fit REST API for real step and heart-rate streams, replacing the
  manual check-in as the primary input
- Cloud Scheduler job that computes insights overnight so the dashboard loads
  instantly instead of calling Vertex on render
- The clinician PDF export the third consent scope already reserves
- BigQuery export for cohort-level analysis once there is more than one user

---

**This is a wellness tracker, not a medical device.** It describes how your own
readings compare to your own history. It does not diagnose, treat, or rule out
any condition.
