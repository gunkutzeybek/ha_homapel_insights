"""Pure (HA-free) analysis layer: rollup models, deterministic analyzers, privacy.

Nothing in this package imports `homeassistant` — so the analyzer logic is unit-
testable on its own. The HA-coupled `collector.py` builds `EntityWindow`s from
recorder history and feeds them here.
"""
