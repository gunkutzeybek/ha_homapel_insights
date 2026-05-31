"""Edge analyzer + rollup + privacy logic (HA-free)."""

from datetime import UTC, datetime

from analysis.left_on import LeftOnAnalyzer
from analysis.models import CandidateSignalData, EntityWindow, OnEvent
from analysis.privacy import apply_privacy, coarse_time_bucket
from analysis.recurring_manual import RecurringManualAnalyzer
from analysis.rollup import StateSpan, build_windows
from analysis.signal_id import deterministic_signal_id


def _dt(day: int, hour: int) -> datetime:
    return datetime(2026, 5, day, hour, 0, tzinfo=UTC)


# ── rollup ──────────────────────────────────────────────────────────────────
def test_build_windows_keeps_only_on_spans() -> None:
    spans = [
        StateSpan("light.a", "on", _dt(1, 8), _dt(1, 9)),
        StateSpan("light.a", "off", _dt(1, 9), _dt(1, 10)),
        StateSpan("switch.b", "open", _dt(1, 8), _dt(1, 12)),
    ]
    windows = {w.entity_id: w for w in build_windows(spans)}
    assert len(windows["light.a"].on_events) == 1
    assert windows["light.a"].on_events[0].duration_s == 3600
    assert windows["switch.b"].domain == "switch"


# ── left_on ───────────────────────────────────────────────────────────────────
def test_left_on_fires_for_long_overnight_stretch() -> None:
    window = EntityWindow(
        "light.porch", "light", [OnEvent(start=_dt(1, 23), duration_s=8 * 3600)]
    )
    signals = LeftOnAnalyzer(min_hours=6).analyze([window])
    assert len(signals) == 1
    assert signals[0].type == "waste.left_on"
    assert signals[0].priority == "high"  # overnight
    assert signals[0].evidence["overnight"] is True
    assert signals[0].evidence["hours_on"] == 8.0


def test_left_on_ignores_short_and_other_domains() -> None:
    short = EntityWindow("light.x", "light", [OnEvent(_dt(1, 10), 3600)])
    sensor = EntityWindow("sensor.y", "sensor", [OnEvent(_dt(1, 1), 9 * 3600)])
    assert LeftOnAnalyzer(min_hours=6).analyze([short, sensor]) == []


# ── recurring_manual ──────────────────────────────────────────────────────────
def test_recurring_manual_fires_on_repeated_daily_hour() -> None:
    events = [OnEvent(start=_dt(day, 19), duration_s=1800) for day in (1, 2, 3, 4)]
    window = EntityWindow("light.living", "light", events)
    signals = RecurringManualAnalyzer(min_days=3).analyze([window])
    assert len(signals) == 1
    assert signals[0].type == "automation.suggest"
    assert signals[0].evidence["days_observed"] == 4
    assert signals[0].evidence["typical_hour"] == 19


def test_recurring_manual_needs_min_days_and_ignores_automated() -> None:
    too_few = EntityWindow("light.a", "light", [OnEvent(_dt(1, 19), 60), OnEvent(_dt(2, 19), 60)])
    automated = EntityWindow(
        "light.b", "light", [OnEvent(_dt(d, 7), 60, manual=False) for d in (1, 2, 3, 4)]
    )
    assert RecurringManualAnalyzer(min_days=3).analyze([too_few, automated]) == []


# ── privacy ───────────────────────────────────────────────────────────────────
def test_privacy_coarsens_hour_and_enforces_consent() -> None:
    sig = CandidateSignalData(
        type="automation.suggest",
        entities=["light.living"],
        evidence={"typical_hour": 19, "days_observed": 4},
    )
    out = apply_privacy([sig])
    assert "typical_hour" not in out[0].evidence
    assert out[0].evidence["typical_time"] == "evening"

    # consent allow-list drops non-consented entities
    assert apply_privacy([sig], allowed_entities={"light.other"}) == []


def test_coarse_time_buckets() -> None:
    assert coarse_time_bucket(8) == "morning"
    assert coarse_time_bucket(14) == "afternoon"
    assert coarse_time_bucket(20) == "evening"
    assert coarse_time_bucket(2) == "night"


# ── deterministic signal id ───────────────────────────────────────────────────
def test_signal_id_stable_and_period_sensitive() -> None:
    a = deterministic_signal_id("unit", "waste.left_on", ["light.a", "light.b"], "2026-W22")
    b = deterministic_signal_id("unit", "waste.left_on", ["light.b", "light.a"], "2026-W22")
    c = deterministic_signal_id("unit", "waste.left_on", ["light.a", "light.b"], "2026-W23")
    assert a == b  # order-independent, same period
    assert a != c  # new period → new id
