"""Analyzer: a device left on while nobody was home.

Emits `waste.on_while_away` — the strongest waste signal, because an entity
running with the house empty is almost never intentional. Relies on the
collector having tagged on-events with `away` from the occupancy timeline; on
setups with no presence data nothing is ever tagged away, so this stays silent.
Deterministic — no LLM.
"""

from __future__ import annotations

from .models import CandidateSignalData, EntityWindow


class OnWhileAwayAnalyzer:
    name = "on_while_away"

    def __init__(self, min_minutes: float = 30.0) -> None:
        self._min_seconds = min_minutes * 60

    def analyze(self, windows: list[EntityWindow]) -> list[CandidateSignalData]:
        out: list[CandidateSignalData] = []
        for w in windows:
            away_events = [
                e for e in w.on_events if e.away and e.duration_s >= self._min_seconds
            ]
            if not away_events:
                continue
            total_away_s = sum(e.duration_s for e in away_events)
            longest = max(away_events, key=lambda e: e.duration_s)
            evidence: dict[str, object] = {
                "domain": w.domain,
                "occurrences": len(away_events),
                "hours_on_while_away": round(total_away_s / 3600, 1),
                "longest_hours": round(longest.duration_s / 3600, 1),
            }
            if w.energy_kwh is not None:
                evidence["energy_kwh"] = round(w.energy_kwh, 2)
            out.append(
                CandidateSignalData(
                    type="waste.on_while_away",
                    entities=[w.entity_id],
                    evidence=evidence,
                    priority="high",
                    area_id=w.area_id,
                )
            )
        return out
