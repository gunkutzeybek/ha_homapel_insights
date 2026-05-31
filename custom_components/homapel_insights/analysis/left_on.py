"""Analyzer: a controllable entity left on for an unusually long stretch.

Emits `waste.left_on` for lights, switches, fans, climate (AC heating/cooling),
and media players (e.g. a TV left on overnight). Overnight stretches are flagged
high priority (likely forgotten). Covers are excluded — a shutter being "open"
for hours is not waste. Deterministic — no LLM (the cost/privacy firewall).
"""

from __future__ import annotations

from .models import CandidateSignalData, EntityWindow

# Domains where a long continuous "on" stretch plausibly means waste. Covers are
# intentionally absent (open != on-cost); recurring_manual handles their routine.
_DOMAINS = {"light", "switch", "fan", "climate", "media_player"}


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
            evidence = {
                "domain": w.domain,
                "hours_on": round(longest.duration_s / 3600, 1),
                "overnight": overnight,
            }
            if w.energy_kwh is not None:
                evidence["energy_kwh"] = round(w.energy_kwh, 2)
            out.append(
                CandidateSignalData(
                    type="waste.left_on",
                    entities=[w.entity_id],
                    evidence=evidence,
                    priority="high" if overnight else "normal",
                    area_id=w.area_id,
                )
            )
        return out
