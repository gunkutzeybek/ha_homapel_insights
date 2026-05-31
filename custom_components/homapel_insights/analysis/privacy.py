"""Privacy minimization (HA-free).

Aggregate, don't ship raw logs. Coarsen precise hours into time-of-day buckets
and enforce the consent allow-list before anything leaves the home.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import replace

from .models import CandidateSignalData


def coarse_time_bucket(hour: int) -> str:
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "night"


def apply_privacy(
    signals: list[CandidateSignalData],
    allowed_entities: Collection[str] | None = None,
) -> list[CandidateSignalData]:
    """Minimize evidence + enforce consent.

    `allowed_entities=None` means whole-home opt-in (everything allowed) — the
    MVP consent model. A set restricts to consented entities (Phase 2).
    """
    out: list[CandidateSignalData] = []
    for s in signals:
        if allowed_entities is not None and not all(e in allowed_entities for e in s.entities):
            continue
        evidence = dict(s.evidence)
        hour = evidence.pop("typical_hour", None)
        if isinstance(hour, int):
            evidence["typical_time"] = coarse_time_bucket(hour)
        out.append(replace(s, evidence=evidence))
    return out
