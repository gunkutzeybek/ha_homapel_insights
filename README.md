# Laris Insights — Edge Integration (`homapel_insights`)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Home Assistant custom component — the edge half of the Laris proactive layer.
Runs inside the user's HA, will collect + aggregate events locally, run
**deterministic** analyzers, minimize for privacy, and upload compact candidate
signals to the cloud. The cloud returns suggestions in the upload response (pull
model), surfaced here as notifications.

Design: [`../proactive_service/PROACTIVE_INSIGHTS_PLAN.md`](../proactive_service/PROACTIVE_INSIGHTS_PLAN.md)
· Build plan: [`../proactive_service/plans/IMPLEMENTATION_PLAN.md`](../proactive_service/plans/IMPLEMENTATION_PLAN.md)

## Status: Phase 2 (cross-domain analysis)

- Config flow with **whole-home opt-in**, cloud endpoint, and the unit `api_key`.
- Hourly poll: read recorder history → deterministic analyzers → privacy
  minimization → upload candidate signals → deliver returned suggestions as
  notifications. The LLM lives only in the cloud; the edge ships aggregated
  signals, never raw telemetry.
- `InsightsUploader` — Bearer-authed POST to `/v1/insights/signals` and
  `/v1/insights/feedback`.
- `homapel_insights.upload_test_signal` service — crafts + uploads one signal to
  verify the end-to-end loop.

### Collected domains & context
- **On/off behaviour**: `light`, `switch`, `fan`, `climate`, `cover`,
  `media_player`.
- **Occupancy context**: a home-vs-away timeline from `person`/`device_tracker`,
  used to tag each on-event with an `away` flag (silent when no trackers exist).
- **Energy context**: per-entity kWh totals from sibling energy sensors on the
  same device.

### Analyzers (all deterministic, HA-free, unit-tested)
- `left_on` → `waste.left_on` (long/overnight on-stretch; lights, switches, fans,
  climate, media players).
- `recurring_manual` → `automation.suggest` (same manual action at the same hour
  on ≥3 days).
- `on_while_away` → `waste.on_while_away` (running while the home is empty).
- `energy_waste` → `waste.energy` (kWh hogs; away energy raises priority).

### Not yet
Per-entity consent allow-list (Phase 3), entity/area-id anonymization,
appliance-health anomaly analyzers (washer/litter numeric trends), and
actionable accept/reject notifications.

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

## Verify end-to-end

1. Bring up `laris_insights` (cloud) pointed at the shared Postgres.
2. Add this integration with a valid Pro unit `api_key` and the cloud URL.
3. Call `homapel_insights.upload_test_signal`; run the cloud synth worker; call
   the service again — a `persistent_notification` should appear.

> **Note:** the cloud ingest must recognize the Phase 2 signal `type`s
> (`waste.on_while_away`, `waste.energy`) and the new `domain`/`energy_kwh`
> evidence keys. The wire envelope (`schema_version`) is unchanged — only the
> set of `type` values and evidence fields grew, which the cloud can treat as
> additive.
