"""HA Store wrapper: last-run cursor + queued feedback (HA-coupled).

Cloud dedupe is handled by deterministic signal ids, so this keeps only the
small local state the edge owns: when we last ran, and feedback actions awaiting
the next upload poll.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.helpers.storage import Store

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_STORAGE_VERSION = 1


class InsightsStore:
    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store = Store(hass, _STORAGE_VERSION, f"{DOMAIN}.{entry_id}")
        self._data: dict[str, Any] = {"feedback_queue": [], "last_run": None}

    async def load(self) -> None:
        stored = await self._store.async_load()
        if stored:
            self._data = stored
        self._data.setdefault("feedback_queue", [])
        self._data.setdefault("last_run", None)

    async def save(self) -> None:
        await self._store.async_save(self._data)

    def queue_feedback(self, suggestion_id: str, action: str) -> None:
        self._data["feedback_queue"].append({"suggestion_id": suggestion_id, "action": action})

    def drain_feedback(self) -> list[dict[str, str]]:
        queued = list(self._data["feedback_queue"])
        self._data["feedback_queue"] = []
        return queued

    @property
    def last_run(self) -> str | None:
        return self._data.get("last_run")

    @last_run.setter
    def last_run(self, value: str) -> None:
        self._data["last_run"] = value
