"""Edge collection/aggregation logic (HA-free): rollup, occupancy, observation
projection onto the §6.1 wire shape, privacy minimization.

There is no edge-side decision layer anymore — the cloud LLM decides, and the
cloud owns dedup (one upserted row per entity). These tests cover the senses:
collect → roll up → project → minimize.
"""

from datetime import UTC, datetime

from analysis.models import EntityWindow, OnEvent
from analysis.observation import on_event_to_wire, to_observation
from analysis.occupancy import build_occupancy, merge_intervals
from analysis.privacy import apply_privacy
from analysis.rollup import StateSpan, build_windows


def _dt(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 5, day, hour, minute, tzinfo=UTC)


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


def test_build_windows_carries_manual_and_area() -> None:
    spans = [StateSpan("light.a", "on", _dt(1, 8), _dt(1, 9), manual=False)]
    windows = {w.entity_id: w for w in build_windows(spans, {"light.a": "salon"})}
    assert windows["light.a"].area_id == "salon"
    assert windows["light.a"].on_events[0].manual is False


# ── observation projection (collector EntityWindow → §6.1 ObservationWindow) ──
def test_on_event_to_wire_maps_all_fields() -> None:
    wire = on_event_to_wire(OnEvent(start=_dt(1, 9, 30), duration_s=7200, manual=False, away=True))
    assert wire == {
        "start": _dt(1, 9, 30).isoformat(),
        "duration_s": 7200,
        "manual": False,
        "away": True,
    }


def test_to_observation_is_a_straight_field_mapping() -> None:
    window = EntityWindow(
        entity_id="climate.salon",
        domain="climate",
        on_events=[OnEvent(start=_dt(1, 23), duration_s=8 * 3600, away=True)],
        area_id="salon",
        energy_kwh=3.25,
    )
    obs = to_observation(window)

    # No id, no timestamps, no presence flag — the cloud owns dedup; envelope owns
    # window bounds + had_presence_data.
    assert "observation_id" not in obs
    assert obs["entity_id"] == "climate.salon"
    assert obs["domain"] == "climate"
    assert obs["area_id"] == "salon"
    assert obs["energy_kwh"] == 3.25  # carried verbatim — no threshold, no verdict
    assert len(obs["on_events"]) == 1
    assert obs["on_events"][0]["away"] is True
    assert obs["on_events"][0]["duration_s"] == 8 * 3600


def test_to_observation_keeps_null_energy_and_empty_events() -> None:
    obs = to_observation(EntityWindow("light.b", "light"))
    assert obs["energy_kwh"] is None
    assert obs["area_id"] is None
    assert obs["on_events"] == []


# ── privacy minimization ──────────────────────────────────────────────────────
def test_privacy_coarsens_on_event_start_to_the_hour() -> None:
    obs = to_observation(
        EntityWindow("light.living", "light", [OnEvent(_dt(1, 19, 42), 1800)])
    )
    [out] = apply_privacy([obs])
    # minute/second precision dropped; floored to 19:00.
    assert out["on_events"][0]["start"] == _dt(1, 19).isoformat()


def test_privacy_enforces_consent_allow_list() -> None:
    living = to_observation(EntityWindow("light.living", "light", [OnEvent(_dt(1, 19), 60)]))
    bedroom = to_observation(EntityWindow("light.bedroom", "light", [OnEvent(_dt(1, 22), 60)]))

    # whole-home opt-in (None) → everything passes through
    assert len(apply_privacy([living, bedroom])) == 2

    # per-entity consent → only the allowed entity survives
    kept = apply_privacy([living, bedroom], allowed_entities={"light.living"})
    assert [o["entity_id"] for o in kept] == ["light.living"]


def test_privacy_does_not_mutate_input() -> None:
    obs = to_observation(EntityWindow("light.a", "light", [OnEvent(_dt(1, 19, 42), 60)]))
    original_start = obs["on_events"][0]["start"]
    apply_privacy([obs])
    assert obs["on_events"][0]["start"] == original_start  # input untouched


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
    assert tl.has_data is True

    # No presence data → never away (conservative), and has_data is reported so
    # the cloud knows absent "away" tags mean "unknown", not "was home".
    empty = build_occupancy([], has_data=False)
    assert empty.has_data is False
    assert empty.away_fraction(_dt(1, 0), _dt(1, 23)) == 0.0
    assert empty.is_away(_dt(1, 0), _dt(1, 23)) is False
