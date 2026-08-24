# Laris Insights — Edge Integration (`homapel_insights`)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Home Assistant custom component — the edge half of the Laris proactive layer.
It runs inside your Home Assistant, reads recorder history on an hourly poll,
aggregates it into per-entity **observation windows**, minimizes them for
privacy, and uploads them to the Laris cloud. The cloud decides which
suggestions are worth making and returns them in the upload response (pull
model); this integration surfaces them as notifications you can accept or
reject.

The LLM lives **only** in the cloud. The edge ships aggregated observations —
never raw telemetry, and never its own verdicts.

Design: [`../proactive_service/PROACTIVE_INSIGHTS_PLAN.md`](../proactive_service/PROACTIVE_INSIGHTS_PLAN.md)
· Build plan: [`../proactive_service/plans/IMPLEMENTATION_PLAN.md`](../proactive_service/plans/IMPLEMENTATION_PLAN.md)

## Setup

Laris Insights is included in the Laris subscription — there is no separate
plan to buy. You need an API key from [laris.homapel.com](https://laris.homapel.com);
it is the **same key** the Homapel Conversation (voice) integration uses.

1. **Install.** In HACS, open the three-dot menu → **Custom repositories**, add
   this repository with category **Integration**, download **Laris Insights**,
   and restart Home Assistant.
2. **Add the integration.** **Settings → Devices & Services → Add Integration →
   Laris Insights**.
3. **Paste your API key.** If you already set up Homapel Conversation, the key
   is prefilled from it — just confirm. The key is checked against the Laris
   cloud before the entry is created, so a wrong key is caught immediately
   instead of failing silently an hour later.
4. **Opt in.** Tick the whole-home consent box. Nothing about your home is
   collected or uploaded without it.

Suggestions start arriving as notifications once the cloud has seen enough
history. Answer **Evet / Hayır** (Yes / No) on the notification: accepted
actions run locally, and either answer is reported back so the cloud stops
suggesting what you turn down.

Once this repository is published to the
[HACS default store](https://hacs.xyz/docs/publish/integration), the
custom-repository step goes away.

### When something needs your attention

- **The key was rotated on the dashboard** → the integration asks you to paste
  the new one (Settings → Devices & Services → *Reconfigure*).
- **The subscription is not active** → a repair issue points you at the
  dashboard. Uploads resume on their own once it is live again.
- **Endpoints** (cloud addresses) can be changed from *Reconfigure* without
  re-entering the key. Leave them alone unless Laris support says otherwise.

## What is collected

- **On/off behaviour**: `light`, `switch`, `fan`, `climate`, `cover`,
  `media_player` — aggregated into on-intervals, not raw state logs.
- **Occupancy context**: a home-vs-away timeline built from `person` /
  `device_tracker`, used only to tag each on-interval with an `away` flag
  (silent when the home has no trackers).
- **Energy context**: per-entity kWh totals from sibling energy sensors on the
  same device.

Entity ids are the most specific thing that leaves the house. Per-entity and
per-area consent is the planned next step; today consent is whole-home.

## Wire contract

`schema_version: 2`, mirroring the cloud's `laris_insights/app/contracts.py`:

- `POST /v1/insights/observations` — the aggregated observation windows; the
  response carries this unit's pending suggestions.
- `POST /v1/insights/feedback` — accepted / rejected / snoozed.

Both authenticate with `Authorization: Bearer <api_key>`.

## Install (dev / manual)

Copy `custom_components/homapel_insights/` into your HA `config/custom_components/`,
restart HA, then add the **Laris Insights** integration.

```bash
pip install -e ".[test]"     # Home Assistant needs a POSIX host (WSL on Windows)
ruff check . && pytest       # both must be green before committing
```

## Verify end-to-end

1. Bring up `laris_insights` (cloud) pointed at the shared Postgres.
2. Add this integration with a real unit `api_key` and the cloud URL.
3. Call `homapel_insights.upload_test_signal`; run the cloud synth worker; call
   the service again — a notification should appear.
