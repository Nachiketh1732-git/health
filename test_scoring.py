"""Regression tests for the readiness composite.

The original formula summed raw deviations across seven metrics. Because
roughly half of them land on their adverse side by chance on any given day,
a completely ordinary day scored in the thirties. These tests pin the fix.
"""

import datetime as dt
import random
import statistics

from app import analytics


def build(seed: int, *, spike: bool = False, tired: bool = False, days: int = 45):
    random.seed(seed)
    today = dt.date.today()
    rows = []
    for i in range(days, 0, -1):
        d = today - dt.timedelta(days=i - 1)
        s, t = spike and i <= 3, tired and i <= 6
        rows.append({
            "date": d.isoformat(),
            "resting_hr": round(random.gauss(57, 2) + (7.5 if s else 0), 1),
            "hrv": round(max(15, random.gauss(54, 6) - (9 if s else 0)), 1),
            "sleep_hours": round(max(3.5, random.gauss(7.2, 0.6) - (1.7 if t else 0)), 1),
            "steps": max(400, int(random.gauss(8000, 1600))),
            "sleep_quality": random.randint(2, 3) if t else random.randint(3, 5),
            "energy": random.randint(2, 3) if t else random.randint(3, 5),
            "stress": random.randint(3, 5) if t else random.randint(1, 3),
        })
    bands = [analytics.build_band(rows, m, today) for m in analytics.METRIC_SPEC]
    return analytics.readiness(bands)


def test_ordinary_days_score_well():
    """Noise must not accumulate. Most unremarkable days should read steady."""
    results = [build(s) for s in range(60)]
    assert statistics.median(r["score"] for r in results) >= 70
    assert sum(r["status"] == "steady" for r in results) >= 40


def test_illness_pattern_is_flagged():
    results = [build(s, spike=True, tired=True) for s in range(40)]
    assert statistics.median(r["score"] for r in results) <= 35
    assert sum(r["status"] == "flag" for r in results) >= 30


def test_scenarios_are_ordered():
    """Each worse scenario must score below the last, not just differ."""
    calm = statistics.median(build(s)["score"] for s in range(40))
    tired = statistics.median(build(s, tired=True)["score"] for s in range(40))
    ill = statistics.median(build(s, spike=True, tired=True)["score"] for s in range(40))
    assert calm > tired > ill


def test_correlated_metrics_do_not_zero_the_score():
    """Resting HR and HRV move together. One physiological event should not
    be counted twice at full weight."""
    assert build(1, spike=True)["score"] > 0


def test_short_history_reports_learning():
    assert build(1, days=4)["score"] is None
    assert build(1, days=4)["status"] == "learning"
