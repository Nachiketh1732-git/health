from __future__ import annotations

import os
from datetime import date

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import analytics
import narrative
import store

app = FastAPI(title="Wellness Analytics API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- auth ----------

def current_user(authorization: str = Header(default="")) -> str:
    """Verifies a Firebase ID token and returns the uid.

    With no GOOGLE_CLOUD_PROJECT set we run in local mode and trust the
    header, which lets you develop without a Firebase project. That branch
    can never fire in Cloud Run because the env var is always present there.
    """
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "Missing bearer token")

    if not store.using_firestore():
        return f"local:{token[:24]}"

    try:
        import firebase_admin
        from firebase_admin import auth as fb_auth

        if not firebase_admin._apps:
            firebase_admin.initialize_app()
        return fb_auth.verify_id_token(token)["uid"]
    except Exception:
        raise HTTPException(401, "Could not verify that sign-in. Try signing in again.")


# ---------- schemas ----------

class Reading(BaseModel):
    date: date
    resting_hr: float | None = Field(default=None, ge=25, le=220)
    hrv: float | None = Field(default=None, ge=1, le=400)
    sleep_hours: float | None = Field(default=None, ge=0, le=24)
    steps: int | None = Field(default=None, ge=0, le=200_000)
    sleep_quality: int | None = Field(default=None, ge=1, le=5)
    energy: int | None = Field(default=None, ge=1, le=5)
    stress: int | None = Field(default=None, ge=1, le=5)


class IngestRequest(BaseModel):
    readings: list[Reading]


class ConsentRequest(BaseModel):
    store_metrics: bool = False
    generate_insights: bool = False
    share_with_clinician: bool = False


# ---------- routes ----------

@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "firestore": store.using_firestore()}


@app.get("/api/consent")
def read_consent(uid: str = Depends(current_user)) -> dict:
    return store.get_consent(uid)


@app.put("/api/consent")
def write_consent(body: ConsentRequest, uid: str = Depends(current_user)) -> dict:
    return store.set_consent(uid, body.model_dump())


@app.post("/api/readings")
def ingest(body: IngestRequest, uid: str = Depends(current_user)) -> dict:
    if not store.has_consent(uid, "store_metrics"):
        raise HTTPException(403, "Turn on 'Store my metrics' before sending data.")
    rows = [r.model_dump(mode="json") for r in body.readings]
    return {"stored": store.put_readings(uid, rows)}


@app.get("/api/readings")
def readings(uid: str = Depends(current_user), limit: int = 120) -> dict:
    return {"readings": store.list_readings(uid, limit)}


@app.get("/api/insights")
def insights(uid: str = Depends(current_user), on: date | None = None) -> dict:
    rows = store.list_readings(uid)
    if not rows:
        return {"empty": True, "message": "No readings yet. Import a file or log today's check-in."}

    day = on or max(date.fromisoformat(str(r["date"])) for r in rows)
    bands = [analytics.build_band(rows, m, day).to_dict() for m in analytics.METRIC_SPEC]
    score = analytics.readiness([analytics.build_band(rows, m, day) for m in analytics.METRIC_SPEC])
    signals = analytics.detect_signals(rows, day)

    summary = (narrative.write_summary(score, bands, signals)
               if store.has_consent(uid, "generate_insights")
               else {"text": "Insights are turned off. Enable them under Data controls.",
                     "source": "disabled"})

    return {"empty": False, "date": day.isoformat(), "readiness": score,
            "bands": bands, "signals": signals, "summary": summary}


@app.delete("/api/me")
def delete_me(uid: str = Depends(current_user)) -> dict:
    store.delete_everything(uid)
    return {"deleted": True}
