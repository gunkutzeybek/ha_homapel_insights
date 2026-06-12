"""Pure (HA-free) collection layer: rollup models, observation projection, privacy.

Nothing in this package imports `homeassistant` — so the logic is unit-testable on
its own. The HA-coupled `collector.py` builds `EntityWindow`s from recorder
history; `observation.py` projects them straight onto the §6.1 wire shape and
`privacy.py` minimizes them. There is no edge-side decision layer — the cloud LLM
analyzes the observations and decides whether any suggestion is warranted.
"""
