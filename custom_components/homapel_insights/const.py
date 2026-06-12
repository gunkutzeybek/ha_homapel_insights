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
