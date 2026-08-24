# Laris Insights

The edge half of the Laris proactive layer. It runs inside your Home Assistant,
aggregates what your home does into compact observation windows, minimizes them
for privacy, and uploads them to the Laris cloud. The cloud decides which
suggestions are worth making and returns them, and this integration surfaces
them as notifications you can accept or reject.

Insights is included in the Laris subscription — there is no separate plan.

## Setup

After installing via HACS and restarting Home Assistant, add the integration
from **Settings → Devices & Services → Add Integration → Laris Insights**, then:

1. Paste the API key from [laris.homapel.com](https://laris.homapel.com). It is
   the same key as the Homapel Conversation integration — if that one is already
   set up, the key is prefilled for you.
2. Tick the whole-home consent box. Nothing is collected or uploaded without it.

The key is validated against the Laris cloud before the entry is created, so a
wrong key is caught right away.
