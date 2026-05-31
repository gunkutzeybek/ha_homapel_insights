"""Analyzer: the same manual action at ~the same time on many days.

Emits `automation.suggest` — the strongest "offer to automate this" signal.
Buckets manual on-events by hour-of-day; fires when one bucket recurs on at
least `min_days` distinct days. Deterministic — no LLM.
"""

from __future__ import annotations

from collections import defaultdict

from .models import CandidateSignalData, EntityWindow


class RecurringManualAnalyzer:
    name = "recurring_manual"

    def __init__(self, min_days: int = 3) -> None:
        self._min_days = min_days

    def analyze(self, windows: list[EntityWindow]) -> list[CandidateSignalData]:
        out: list[CandidateSignalData] = []
        for w in windows:
            days_by_hour: dict[int, set] = defaultdict(set)
            count_by_hour: dict[int, int] = defaultdict(int)
            for e in w.on_events:
                if not e.manual:
                    continue
                days_by_hour[e.start.hour].add(e.start.date())
                count_by_hour[e.start.hour] += 1

            if not days_by_hour:
                continue
            best_hour = max(days_by_hour, key=lambda h: len(days_by_hour[h]))
            days_observed = len(days_by_hour[best_hour])
            if days_observed < self._min_days:
                continue
            out.append(
                CandidateSignalData(
                    type="automation.suggest",
                    entities=[w.entity_id],
                    evidence={
                        "domain": w.domain,
                        "pattern": "recurring_on",
                        "typical_hour": best_hour,
                        "days_observed": days_observed,
                        "count": count_by_hour[best_hour],
                    },
                    area_id=w.area_id,
                )
            )
        return out
