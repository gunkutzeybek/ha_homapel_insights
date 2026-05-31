"""Analyzer: a device that drew a meaningful amount of energy over the window.

Emits `waste.energy` for entities whose total kWh (from a sibling energy sensor
the collector mapped in) crosses a threshold. Energy consumed while the home was
away raises the priority — that's the actionable waste. Entities with no energy
data are skipped entirely. Deterministic — no LLM.
"""

from __future__ import annotations

from .models import CandidateSignalData, EntityWindow


class EnergyWasteAnalyzer:
    name = "energy_waste"

    def __init__(self, min_kwh: float = 1.0) -> None:
        self._min_kwh = min_kwh

    def analyze(self, windows: list[EntityWindow]) -> list[CandidateSignalData]:
        out: list[CandidateSignalData] = []
        for w in windows:
            if w.energy_kwh is None or w.energy_kwh < self._min_kwh:
                continue
            total_s = sum(e.duration_s for e in w.on_events)
            away_s = sum(e.duration_s for e in w.on_events if e.away)
            away_fraction = round(away_s / total_s, 2) if total_s > 0 else 0.0
            out.append(
                CandidateSignalData(
                    type="waste.energy",
                    entities=[w.entity_id],
                    evidence={
                        "domain": w.domain,
                        "energy_kwh": round(w.energy_kwh, 2),
                        "away_fraction": away_fraction,
                    },
                    priority="high" if away_fraction >= 0.5 else "normal",
                    area_id=w.area_id,
                )
            )
        return out
