"""Personal-baseline analytics.

The core idea: nothing is compared to a population norm. Every metric is
compared to *this user's own* rolling baseline, which is what makes the
output feel personal and keeps us well clear of diagnostic claims.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from typing import Iterable, Literal

BASELINE_WINDOW_DAYS = 30
MIN_DAYS_FOR_BASELINE = 7

Status = Literal["steady", "watch", "flag", "learning"]

# direction = which way is "worse" for this metric
METRIC_SPEC = {
    "resting_hr":    {"label": "Resting heart rate", "unit": "bpm",   "direction": "up"},
    "hrv":           {"label": "Heart rate variability", "unit": "ms", "direction": "down"},
    "sleep_hours":   {"label": "Sleep",              "unit": "h",     "direction": "down"},
    "steps":         {"label": "Steps",              "unit": "",      "direction": "down"},
    "sleep_quality": {"label": "Sleep quality",      "unit": "/5",    "direction": "down"},
    "energy":        {"label": "Energy",             "unit": "/5",    "direction": "down"},
    "stress":        {"label": "Stress",             "unit": "/5",    "direction": "up"},
}


@dataclass
class Band:
    """One metric rendered as a lab-report style reference band."""
    metric: str
    label: str
    unit: str
    value: float | None
    baseline_mean: float | None
    baseline_low: float | None
    baseline_high: float | None
    deviation: float | None      # signed z-score
    status: Status
    note: str

    def to_dict(self) -> dict:
        return asdict(self)


def _window(readings: list[dict], metric: str, end: date, days: int) -> list[float]:
    start = end - timedelta(days=days)
    out = []
    for r in readings:
        d = r["date"] if isinstance(r["date"], date) else date.fromisoformat(r["date"])
        if start <= d < end and r.get(metric) is not None:
            out.append(float(r[metric]))
    return out


def _status_from(z: float, direction: str) -> Status:
    """Two thresholds, deliberately conservative. 1.5 SD nudges, 2.5 SD flags."""
    adverse = z if direction == "up" else -z
    if adverse >= 2.5:
        return "flag"
    if adverse >= 1.5:
        return "watch"
    return "steady"


def build_band(readings: list[dict], metric: str, on: date) -> Band:
    spec = METRIC_SPEC[metric]
    today = [r for r in readings
             if (r["date"] if isinstance(r["date"], date) else date.fromisoformat(r["date"])) == on]
    value = float(today[0][metric]) if today and today[0].get(metric) is not None else None
    history = _window(readings, metric, on, BASELINE_WINDOW_DAYS)

    if len(history) < MIN_DAYS_FOR_BASELINE:
        return Band(
            metric=metric, label=spec["label"], unit=spec["unit"], value=value,
            baseline_mean=None, baseline_low=None, baseline_high=None,
            deviation=None, status="learning",
            note=f"Needs {MIN_DAYS_FOR_BASELINE - len(history)} more days to learn your range.",
        )

    mean = statistics.fmean(history)
    sd = statistics.pstdev(history) or 0.001
    low, high = mean - sd, mean + sd

    if value is None:
        return Band(
            metric=metric, label=spec["label"], unit=spec["unit"], value=None,
            baseline_mean=round(mean, 1), baseline_low=round(low, 1),
            baseline_high=round(high, 1), deviation=None, status="learning",
            note="No reading logged today.",
        )

    z = (value - mean) / sd
    status = _status_from(z, spec["direction"])
    delta = value - mean
    arrow = "above" if delta >= 0 else "below"
    note = f"{abs(round(delta, 1))}{spec['unit']} {arrow} your 30-day average."

    return Band(
        metric=metric, label=spec["label"], unit=spec["unit"], value=round(value, 1),
        baseline_mean=round(mean, 1), baseline_low=round(low, 1),
        baseline_high=round(high, 1), deviation=round(z, 2), status=status, note=note,
    )


DEADBAND_SD = 0.75      # ordinary noise below this costs nothing
PENALTY_PER_SD = 16.0
MAX_ADVERSE_SD = 3.5


def readiness(bands: Iterable[Band]) -> dict:
    """A single 0-100 composite. Deliberately simple and explainable —
    a user should be able to reconstruct it from the bands on screen.

    Two guards, both learned the hard way from the sample data:

    The deadband. On any given day roughly half of seven metrics land on
    their adverse side by chance. Summing those raw deviations penalised a
    completely ordinary day into the thirties. Nothing under 0.75 SD counts.

    The cap. Metrics that move together — resting HR and HRV almost always
    do — otherwise compound and drive the score to zero on a merely bad day.
    """
    scored = [b for b in bands if b.deviation is not None]
    if not scored:
        return {"score": None, "status": "learning",
                "note": "Log a few more days and this will start working."}

    penalty = 0.0
    for b in scored:
        adverse = b.deviation if METRIC_SPEC[b.metric]["direction"] == "up" else -b.deviation
        excess = min(adverse, MAX_ADVERSE_SD) - DEADBAND_SD
        penalty += max(0.0, excess) * PENALTY_PER_SD

    score = int(max(0, min(100, round(100 - penalty))))
    status: Status = "steady" if score >= 70 else "watch" if score >= 45 else "flag"
    driver = max(scored, key=lambda b: (b.deviation if METRIC_SPEC[b.metric]["direction"] == "up"
                                        else -b.deviation))
    note = ("Everything sits inside your usual range." if status == "steady"
            else f"Mostly driven by {driver.label.lower()}.")
    return {"score": score, "status": status, "note": note,
            "contributors": [b.metric for b in scored]}


def detect_signals(readings: list[dict], on: date) -> list[dict]:
    """Multi-day pattern rules. These are the ones worth surfacing as alerts
    because a single-day band would miss them."""
    signals = []

    sleep = _window(readings, "sleep_hours", on, 7)
    if len(sleep) >= 5:
        debt = sum(max(0.0, 7.5 - s) for s in sleep)
        if debt >= 6:
            signals.append({
                "id": "sleep_debt",
                "title": "Sleep debt building",
                "detail": f"You're about {round(debt, 1)} hours short over the last week.",
                "severity": "watch",
            })

    rhr_recent = _window(readings, "resting_hr", on + timedelta(days=1), 3)
    rhr_base = _window(readings, "resting_hr", on - timedelta(days=3), 21)
    if len(rhr_recent) >= 3 and len(rhr_base) >= 10:
        drift = statistics.fmean(rhr_recent) - statistics.fmean(rhr_base)
        if drift >= 5:
            signals.append({
                "id": "rhr_drift",
                "title": "Resting heart rate is elevated",
                "detail": f"Up {round(drift, 1)} bpm across three days versus your usual.",
                "severity": "flag",
            })

    steps = _window(readings, "steps", on + timedelta(days=1), 5)
    if len(steps) >= 5 and statistics.fmean(steps) < 3000:
        signals.append({
            "id": "low_movement",
            "title": "Movement has dropped off",
            "detail": "Under 3,000 steps a day for five days running.",
            "severity": "watch",
        })

    return signals
