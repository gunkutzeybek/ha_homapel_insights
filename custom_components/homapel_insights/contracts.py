"""Edge-side mirror of the §6 wire contracts (kept in sync with the cloud's
app/contracts.py). Plain dicts — Home Assistant core ships no pydantic — but the
shapes and `schema_version` are identical and must be versioned in lock-step.

§6.1 is now an ObservationUploadRequest of aggregated EntityWindow rollups, NOT
edge-computed verdicts. The cloud LLM does the analysis; the edge only ships
observations.
"""

from __future__ import annotations

from datetime import datetime

from .analysis.models import EntityWindow
from .analysis.observation import to_observation
from .const import SCHEMA_VERSION


def build_observation_window(window: EntityWindow) -> dict:
    """Build one §6.1 ObservationWindow from an EntityWindow.

    Straight field mapping — no analysis, no thresholds, no id (the cloud owns
    dedup, upserting one row per entity keyed on uuid5(unit_id, entity_id)).
    """
    return to_observation(window)


def build_observation_upload_request(
    *,
    window_start: datetime,
    window_end: datetime,
    had_presence_data: bool,
    observations: list[dict],
) -> dict:
    """Build a §6.1 ObservationUploadRequest body.

    `had_presence_data` tells the cloud whether any person/device_tracker history
    existed this tick, so it can tell "no away tags because everyone was home"
    from "no away tags because we have no presence data at all".
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "had_presence_data": had_presence_data,
        "observations": observations,
    }
