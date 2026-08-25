"""Constants for the Laris Insights edge integration."""

from datetime import timedelta

DOMAIN = "homapel_insights"

# Config entry keys
CONF_CLOUD_BASE_URL = "cloud_base_url"
CONF_API_KEY = "api_key"
CONF_OPT_IN = "opt_in"
# Where the key is validated (the voice backend, agentic_service) and the unit
# id that validation returns — the entry's unique_id since v0.4.0.
CONF_VOICE_API_BASE = "voice_api_base"
CONF_UNIT_ID = "unit_id"

# Phase 0 default cloud endpoint base. Override per-deployment in the config flow.
DEFAULT_CLOUD_BASE_URL = "https://insights.api.homapel.com"

# The Laris cloud API that owns units and api_keys. Same host the voice
# integration talks to; `GET /v1/units/status` is the cheap key check the config
# flow uses. Overridable per entry (staging installs).
DEFAULT_VOICE_API_BASE = "https://api.homapel.com"
# Seconds to wait for that check before calling it a connection failure.
STATUS_TIMEOUT = 10

# Where the customer buys the subscription and reads/rotates the API key.
DASHBOARD_URL = "https://laris.homapel.com"

# The voice integration (homapel.agentic_assistant). It stores the SAME api_key
# under the same subscription, so the config flow offers to reuse it instead of
# making the customer paste the key twice.
VOICE_DOMAIN = "homapel_conversation"
VOICE_CONF_API_KEY = "api_key"
VOICE_CONF_API_BASE = "api_base"

# Repair issue raised from the upload loop on a 403 — the subscription is not
# live (suspended / dormant). A 401 has no issue of its own: it starts a reauth
# flow, which HA already renders as a fixable repair.
ISSUE_UNIT_NOT_ACTIVE = "unit_not_active"

# Pull/upload cadence. Periodic-only for MVP (recommended in the plan); live
# streaming is deferred to a later safety allowlist.
DEFAULT_POLL_INTERVAL = timedelta(hours=1)

# Wire contract version (must match the cloud's app.contracts.SCHEMA_VERSION).
# v2: edge ships aggregated EntityWindow observations (ObservationUploadRequest);
# the cloud LLM does the deciding. v1 shipped edge-computed CandidateSignals.
SCHEMA_VERSION = 2

# Service exposed for end-to-end verification: craft + upload one observation.
SERVICE_UPLOAD_TEST_SIGNAL = "upload_test_signal"

# Actionable notification wiring (mobile-app Companion only).
# Buttons fire this event when tapped; the encoded action string carries the
# verb + suggestion id back through the feedback queue.
EVENT_MOBILE_APP_NOTIFICATION_ACTION = "mobile_app_notification_action"
# Button action string format: "homapel_insights__<verb>::<suggestion_id>".
ACTION_PREFIX = f"{DOMAIN}__"
ACTION_SEPARATOR = "::"
# Button verb tokens embedded in the action string (what the user tapped).
BTN_ACCEPT = "accept"
BTN_REJECT = "reject"

# Feedback verbs sent to the cloud /feedback endpoint. These MUST match the
# cloud's FeedbackActionLiteral (app/contracts.py): accepted | rejected | snoozed.
FEEDBACK_ACCEPTED = "accepted"
FEEDBACK_REJECTED = "rejected"

# Suggestion action kinds (mirror of the cloud's SuggestionAction.kind).
#   install_automation → install a standing HA automation (persists, recurs);
#                        carries `automation_draft`.
#   run_action         → run a ONE-TIME action now on the user's "yes"; carries
#                        `action_payload` of shape {"sequence": [...]}. Not persisted.
#   info_only / dismiss → not actionable; delivered without Accept/Reject buttons.
# The cloud's SuggestionAction contract supports all of these; the edge executor
# handles install_automation + run_action (see executor.py).
KIND_INSTALL_AUTOMATION = "install_automation"
KIND_RUN_ACTION = "run_action"
KIND_INFO_ONLY = "info_only"
KIND_DISMISS = "dismiss"
# Kinds that warrant Accept/Reject buttons and an execution on accept.
ACTIONABLE_KINDS = frozenset({KIND_INSTALL_AUTOMATION, KIND_RUN_ACTION})

# Notification button labels live in strings.json (`common`) so they follow the
# customer's HA language instead of being hardcoded Turkish.
TRANSLATION_CATEGORY_COMMON = "common"
BTN_ACCEPT_TRANSLATION_KEY = "notification_accept"
BTN_REJECT_TRANSLATION_KEY = "notification_reject"
# Used only if the translation cache has nothing (never in a normal HA).
BTN_ACCEPT_FALLBACK = "Evet"
BTN_REJECT_FALLBACK = "Hayır"
