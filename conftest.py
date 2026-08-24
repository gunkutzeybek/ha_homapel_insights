"""Test bootstrap.

Two kinds of tests live here:

* `tests/test_analyzers.py` — the HA-free collection/aggregation logic. It lives
  under `custom_components/homapel_insights/analysis/` and imports no
  `homeassistant` symbols, so that directory goes on `sys.path` and the tests
  import `analysis.*` directly, without triggering the package __init__ (which
  does need HA).
* `tests/test_config_flow.py` — the config flow, driven by a real HA instance
  from `pytest-homeassistant-custom-component`.

The analysis path is APPENDED, never prepended: the integration directory holds
modules with names as generic as `const` and `storage`, and they must not shadow
anything Home Assistant imports.
"""

import logging
import pathlib
import sys

# The HA test harness turns SQLAlchemy's engine logging on; the stub recorder
# these tests run against would then narrate every INSERT.
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

_INTEGRATION_DIR = (
    pathlib.Path(__file__).resolve().parent / "custom_components" / "homapel_insights"
)
sys.path.append(str(_INTEGRATION_DIR))
