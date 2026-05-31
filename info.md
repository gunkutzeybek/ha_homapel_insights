# Laris Insights

The edge half of the Laris proactive layer. Runs inside your Home Assistant,
collects and aggregates events locally, runs **deterministic** analyzers,
minimizes for privacy, and uploads compact candidate signals to the cloud. The
cloud returns suggestions in the upload response, surfaced here as
notifications.

## Configuration

After installing via HACS and restarting Home Assistant, add the integration
from **Settings → Devices & Services → Add Integration → Laris Insights**.
You'll provide a whole-home opt-in, the cloud endpoint, and your unit `api_key`.
