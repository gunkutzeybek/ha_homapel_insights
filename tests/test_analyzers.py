"""Edge analyzer + rollup + privacy logic (HA-free)."""

from datetime import UTC, datetime

from analysis.energy_waste import EnergyWasteAnalyzer
from analysis.left_on import LeftOnAnalyzer
from analysis.models import CandidateSignalData, EntityWindow, OnEvent
from analysis.occupancy import build_occupancy, merge_intervals
from analysis.on_while_away import OnWhileAwayAnalyzer
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
    cover = EntityWindow("cover.shutter", "cover", [OnEvent(_dt(1, 1), 9 * 3600)])
    assert LeftOnAnalyzer(min_hours=6).analyze([short, sensor, cover]) == []


def test_left_on_covers_climate_and_media_and_reports_domain_energy() -> None:
    tv = EntityWindow(
        "media_player.salon", "media_player", [OnEvent(_dt(1, 23), 7 * 3600)],
        energy_kwh=2.345,
    )
    ac = EntityWindow("climate.salon", "climate", [OnEvent(_dt(1, 12), 8 * 3600)])
    signals = {s.entities[0]: s for s in LeftOnAnalyzer(min_hours=6).analyze([tv, ac])}
    assert signals["media_player.salon"].evidence["domain"] == "media_player"
    assert signals["media_player.salon"].evidence["energy_kwh"] == 2.35
    assert signals["climate.salon"].evidence["domain"] == "climate"


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


# ── occupancy ─────────────────────────────────────────────────────────────────
def test_merge_intervals_unions_overlaps() -> None:
    merged = merge_intervals(
        [(_dt(1, 8), _dt(1, 10)), (_dt(1, 9), _dt(1, 12)), (_dt(1, 14), _dt(1, 15))]
    )
    assert merged == [(_dt(1, 8), _dt(1, 12)), (_dt(1, 14), _dt(1, 15))]


def test_occupancy_away_fraction_and_no_data_assumes_home() -> None:
    # Present 08:00–10:00; ask about 09:00–11:00 → half the span was away.
    tl = build_occupancy([(_dt(1, 8), _dt(1, 10))])
    assert tl.away_fraction(_dt(1, 9), _dt(1, 11)) == 0.5
    assert tl.is_away(_dt(1, 10), _dt(1, 12)) is True  # fully away
    assert tl.is_away(_dt(1, 8), _dt(1, 10)) is False  # fully home

    # No presence data → never away (conservative).
    empty = build_occupancy([], has_data=False)
    assert empty.away_fraction(_dt(1, 0), _dt(1, 23)) == 0.0
    assert empty.is_away(_dt(1, 0), _dt(1, 23)) is False


# ── on_while_away ─────────────────────────────────────────────────────────────
def test_on_while_away_fires_only_for_away_events() -> None:
    w = EntityWindow(
        "switch.garden", "switch",
        [OnEvent(_dt(1, 9), 2 * 3600, away=True), OnEvent(_dt(2, 9), 2 * 3600, away=False)],
        area_id="garden", energy_kwh=1.2,
    )
    signals = OnWhileAwayAnalyzer(min_minutes=30).analyze([w])
    assert len(signals) == 1
    assert signals[0].type == "waste.on_while_away"
    assert signals[0].priority == "high"
    assert signals[0].evidence["occurrences"] == 1
    assert signals[0].evidence["hours_on_while_away"] == 2.0
    assert signals[0].evidence["energy_kwh"] == 1.2


def test_on_while_away_silent_without_away_events() -> None:
    w = EntityWindow("light.a", "light", [OnEvent(_dt(1, 9), 5 * 3600, away=False)])
    assert OnWhileAwayAnalyzer().analyze([w]) == []


# ── energy_waste ──────────────────────────────────────────────────────────────
def test_energy_waste_thresholds_and_away_priority() -> None:
    low = EntityWindow("switch.a", "switch", [OnEvent(_dt(1, 9), 3600)], energy_kwh=0.4)
    no_energy = EntityWindow("light.b", "light", [OnEvent(_dt(1, 9), 3600)])
    away = EntityWindow(
        "switch.heater", "switch",
        [OnEvent(_dt(1, 9), 3600, away=True), OnEvent(_dt(2, 9), 3600, away=False)],
        energy_kwh=5.0,
    )
    signals = EnergyWasteAnalyzer(min_kwh=1.0).analyze([low, no_energy, away])
    assert len(signals) == 1
    assert signals[0].type == "waste.energy"
    assert signals[0].evidence["energy_kwh"] == 5.0
    assert signals[0].evidence["away_fraction"] == 0.5
    assert signals[0].priority == "high"


# ── deterministic signal id ───────────────────────────────────────────────────
def test_signal_id_stable_and_period_sensitive() -> None:
    a = deterministic_signal_id("unit", "waste.left_on", ["light.a", "light.b"], "2026-W22")
    b = deterministic_signal_id("unit", "waste.left_on", ["light.b", "light.a"], "2026-W22")
    c = deterministic_signal_id("unit", "waste.left_on", ["light.a", "light.b"], "2026-W23")
    assert a == b  # order-independent, same period
    assert a != c  # new period → new id
