"""Analyzer: a light/switch/fan left on for an unusually long stretch.

Emits `waste.left_on`. Overnight stretches are flagged high priority (likely
forgotten). Deterministic — no LLM (the cost/privacy firewall).
"""

from __future__ import annotations

from .models import CandidateSignalData, EntityWindow

_DOMAINS = {"light", "switch", "fan"}


class LeftOnAnalyzer:
    name = "left_on"

    def __init__(self, min_hours: float = 6.0) -> None:
        self._min_seconds = min_hours * 3600

    def analyze(self, windows: list[EntityWindow]) -> list[CandidateSignalData]:
        out: list[CandidateSignalData] = []
        for w in windows:
            if w.domain not in _DOMAINS or not w.on_events:
                continue
            longest = max(w.on_events, key=lambda e: e.duration_s)
            if longest.duration_s < self._min_seconds:
                continue
            # "Turned on late / overnight" heuristic — refined in a later phase.
            overnight = longest.start.hour >= 22 or longest.start.hour < 6
            out.append(
                CandidateSignalData(
                    type="waste.left_on",
                    entities=[w.entity_id],
                    evidence={
                        "hours_on": round(longest.duration_s / 3600, 1),
                        "overnight": overnight,
                    },
                    priority="high" if overnight else "normal",
                    area_id=w.area_id,
                )
            )
        return out
