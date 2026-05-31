# Laris Insights — Edge Integration (`homapel_insights`)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Home Assistant custom component — the edge half of the Laris proactive layer.
Runs inside the user's HA, will collect + aggregate events locally, run
**deterministic** analyzers, minimize for privacy, and upload compact candidate
signals to the cloud. The cloud returns suggestions in the upload response (pull
model), surfaced here as notifications.

Design: [`../proactive_service/PROACTIVE_INSIGHTS_PLAN.md`](../proactive_service/PROACTIVE_INSIGHTS_PLAN.md)
· Build plan: [`../proactive_service/plans/IMPLEMENTATION_PLAN.md`](../proactive_service/plans/IMPLEMENTATION_PLAN.md)

## Status: Phase 0 (skeleton)

- Config flow with **whole-home opt-in**, cloud endpoint, and the unit `api_key`.
- `InsightsUploader` — Bearer-authed POST to `/v1/insights/signals`, parses
  pending suggestions from the response.
- `deliver_suggestions` — fires `persistent_notification` per suggestion.
- `homapel_insights.upload_test_signal` service — crafts + uploads one signal to
  verify the end-to-end loop.

### Not yet (Phase 1)
`collector.py` (recorder history), `rollup.py`, `analyzers/` (`left_on`,
`recurring_manual`), `privacy.py`, `storage.py` (Store-backed cursor + dedupe),
and actionable accept/reject notifications.

## Install via HACS

1. In HACS, open the three-dot menu → **Custom repositories**.
2. Add this repository's URL with category **Integration**.
3. Search for **Laris Insights** in HACS, download it, and restart Home Assistant.
4. Add the **Laris Insights** integration from **Settings → Devices & Services**
   and opt in.

Once the repository is published to the [HACS default store](https://hacs.xyz/docs/publish/integration),
the custom-repository step is no longer needed.

## Install (dev / manual)

Copy `custom_components/homapel_insights/` into your HA `config/custom_components/`,
restart HA, then add the **Laris Insights** integration and opt in.

## Verify Phase 0

1. Bring up `laris_insights` (cloud) pointed at the shared Postgres.
2. Add this integration with a valid Pro unit `api_key` and the cloud URL.
3. Call `homapel_insights.upload_test_signal`; run the cloud synth worker; call
   the service again — a `persistent_notification` should appear.
