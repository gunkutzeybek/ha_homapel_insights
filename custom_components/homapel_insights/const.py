"""Constants for the Laris Insights edge integration."""

from datetime import timedelta

DOMAIN = "homapel_insights"

# Config entry keys
CONF_CLOUD_BASE_URL = "cloud_base_url"
CONF_API_KEY = "api_key"
CONF_OPT_IN = "opt_in"

# Phase 0 default cloud endpoint base. Override per-deployment in the config flow.
DEFAULT_CLOUD_BASE_URL = "https://insights.api.homapel.com"

# Pull/upload cadence. Periodic-only for MVP (recommended in the plan); live
# streaming is deferred to a later safety allowlist.
DEFAULT_POLL_INTERVAL = timedelta(hours=1)

# Wire contract version (must match the cloud's app.contracts.SCHEMA_VERSION).
SCHEMA_VERSION = 1

# Service exposed for Phase 0 end-to-end verification: craft + upload one signal.
SERVICE_UPLOAD_TEST_SIGNAL = "upload_test_signal"
