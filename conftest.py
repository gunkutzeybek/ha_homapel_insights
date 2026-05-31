"""Expose the HA-free `analysis` subpackage for unit tests.

The analyzers live under `custom_components/homapel_insights/analysis/` and import
no `homeassistant` symbols, so we put that integration dir on sys.path and import
`analysis.*` directly — without triggering the package __init__ (which does need HA).
"""

import pathlib
import sys

_INTEGRATION_DIR = (
    pathlib.Path(__file__).resolve().parent / "custom_components" / "homapel_insights"
)
sys.path.insert(0, str(_INTEGRATION_DIR))
