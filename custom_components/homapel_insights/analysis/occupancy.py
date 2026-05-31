"""Occupancy timeline (HA-free).

Merges the "present" intervals of every tracked person/device into a single
home-vs-away timeline, then answers "was the home empty during [start, end]?".

Conservative by design: with no presence data at all the timeline reports
`away_fraction == 0` (assume home), so the `on_while_away` analyzer never fires
on a setup that simply has no trackers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


def merge_intervals(
    intervals: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    """Union overlapping/adjacent (start, end) intervals; drop empty ones."""
    cleaned = [(s, e) for s, e in intervals if e > s]
    if not cleaned:
        return []
    cleaned.sort(key=lambda iv: iv[0])
    merged = [cleaned[0]]
    for start, end in cleaned[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


@dataclass
class OccupancyTimeline:
    """Intervals during which at least one tracked person/device was home."""

    present_intervals: list[tuple[datetime, datetime]]
    has_data: bool = True

    def away_fraction(self, start: datetime, end: datetime) -> float:
        """Fraction of [start, end] during which the home was empty.

        Returns 0.0 (assume home) when there is no presence data or the span is
        degenerate, so callers never flag "away" on absent evidence.
        """
        total = (end - start).total_seconds()
        if total <= 0 or not self.has_data:
            return 0.0
        covered = 0.0
        for a, b in self.present_intervals:
            lo = max(a, start)
            hi = min(b, end)
            if hi > lo:
                covered += (hi - lo).total_seconds()
        return max(0.0, 1.0 - covered / total)

    def is_away(self, start: datetime, end: datetime, threshold: float = 0.5) -> bool:
        return self.away_fraction(start, end) >= threshold


def build_occupancy(
    present_intervals: list[tuple[datetime, datetime]], *, has_data: bool = True
) -> OccupancyTimeline:
    """Build a timeline from raw per-tracker present intervals."""
    return OccupancyTimeline(merge_intervals(present_intervals), has_data=has_data)
