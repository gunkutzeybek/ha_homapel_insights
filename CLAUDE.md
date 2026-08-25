# CLAUDE.md

Guidance for Claude (and humans) working in this repository.

---

## 1. What this is

**Laris Insights — edge** (`custom_components/homapel_insights/`, HA domain `homapel_insights`): the Home Assistant custom integration half of the **Laris** proactive layer. It runs inside the customer's HA, reads recorder history on an hourly poll, builds aggregated per-entity **observation windows** (on/off behaviour, home-vs-away context, energy context), minimizes them for privacy, uploads them to the cloud (`laris_insights`), and surfaces the suggestions the cloud returns as notifications (with accept/reject feedback and, for some suggestions, an on-edge action). The LLM lives **only** in the cloud; this side ships aggregates, never raw telemetry.

**Laris** is Homapel's voice-first smart-home AI. Sibling repos under `D:\Homapel\Projects\Aris\`: `agentic_service` (backend — **its `CLAUDE.md` §1a is the canonical business-model statement**), `laris_insights` (the cloud half, owns the ingest API), `homapel.agentic_assistant` (the voice integration, same API key), `dashboard`, `proactive_service` (design docs).

---

## 2. Business model & onboarding — B2C (decided 2026-08-23)

Laris was designed B2B (installer-provisioned homes, Basic/Pro plans, insights = **Pro-only**). **That is retired.** Laris is sold **B2C** — directly and through dealers — as **one subscription** (₺550/mo). The customer signs up on the dashboard, pays, is shown their **API key**, installs HA (or uses a Homapel-sold HA server), installs the Laris integrations through HACS and pastes the key. **The same key** configures `homapel_conversation` and this integration. Insights is **included in the plan**.

### Target customer path

1. HACS → custom repository (later: HACS default store) → install **Laris Insights** → restart.
2. Add the integration → paste the API key from `laris.homapel.com` → opt in to whole-home collection.
3. Suggestions appear as HA notifications once the cloud has enough history; the customer answers Evet/Hayır (Yes/No) and feedback goes back to the cloud.

### What exists today vs. what is left (this repo)

Onboarding was built out for B2C on 2026-08-24 (branch `b2c-onboarding`).

| Area | Today | Left to do |
|---|---|---|
| Config flow | Validates the key at setup against the voice backend's `GET /v1/units/status` (`voice_api.py`), prefills it from the `homapel_conversation` entry, and keeps the whole-home opt-in as the first gate — no network call without consent. Errors (`invalid_auth`, `forbidden`, `cannot_connect`, `unknown`, `consent_required`) in TR + EN | — |
| Reauth / reconfigure | `async_step_reauth` swaps a key rotated on the dashboard (the uploader starts it on a 401); `async_step_reconfigure` moves `cloud_base_url` / `voice_api_base` and re-checks the stored key | — |
| Entry identity | `unique_id` is the `unit_id` from `/v1/units/status`. Entries created before that (keyed on the api_key) are backfilled on the next setup — a rejected key raises `ConfigEntryAuthFailed`, an unreachable cloud `ConfigEntryNotReady` | Drop the backfill once no pre-0.4.0 entry can exist |
| Copy | "Your Laris API key (from the dashboard — the same one as Homapel Conversation)" in `strings.json` + `translations/{en,tr}.json`; README/info.md are a self-install guide with no "Pro unit" left | — |
| Cloud gate | The cloud gates on ACTIVE only (no Pro tier). A `403` from either endpoint raises the `unit_not_active` repair issue pointing at the dashboard; the next successful call clears it. `/feedback`'s `not_your_suggestion` 403 is excluded | — |
| Default cloud URL | Still `https://insights.api.homapel.com` (`const.py`) — nothing answers there; Caddy routes `/v1/insights/*` on the main API host. `voice_api_base` defaults to `https://api.homapel.com`, the host the voice integration uses | Set `DEFAULT_CLOUD_BASE_URL` to the real production host once decided; keep the field as an override |
| Consent granularity | One whole-home toggle | Per-entity / per-area consent (Phase 3) |
| Docs & contracts | Feedback posts `const.SCHEMA_VERSION` (2); README documents `/v1/insights/observations` + `/v1/insights/feedback` | — |

Dealers (planned, not built) have no footprint here.

---

## 3. Core principles

- **Privacy first.** Aggregate, don't ship raw logs. Explicit whole-home opt-in today; per-entity/area consent is the planned next step. Entity ids are the most specific thing that leaves the home.
- **Cost is bounded by the edge.** The hourly cadence, the 14-day lookback and the observation shape decide what the cloud LLM ever sees — change them consciously.
- **Don't be annoying.** Notification volume, snooze and rejection handling are product behaviour, not polish.
- **Wire contracts are shared.** `const.py`/upload models mirror `laris_insights/app/contracts.py` (`SCHEMA_VERSION = 2`); a change lands in both repos together.

---

## 4. Repository map & commands

```
custom_components/homapel_insights/
  __init__.py        entry setup (opt-in gate → unit_id backfill), hourly poll
                     (recorder history → analysis → upload → deliver)
  config_flow.py     user / reauth / reconfigure steps; validates the key, prefills it
                     from homapel_conversation, keys the entry on unit_id
  voice_api.py       GET /v1/units/status — the cheap key check (agentic_service)
  uploader.py        POST /v1/insights/observations · POST /v1/insights/feedback (Bearer
                     api_key); 401 → reauth, 403 → repair issue
  analysis/          HA-free observation builders (unit-tested via conftest sys.path shim)
  delivery.py        mobile-app notifications with translated Accept/Reject actions
  executor.py        on-edge execution of accepted actions
  storage.py         HA Store for local state
  const.py, strings.json, translations/{en,tr}.json, manifest.json (requirements: [])
tests/test_analyzers.py     HA-free analysis logic
tests/test_config_flow.py   the flow, on a real HA (pytest-homeassistant-custom-component)
pyproject.toml       ruff (py312, line 100, E,F,I,N,UP,B,SIM) + pytest (asyncio auto) +
                     the `test` extra pinning pytest-homeassistant-custom-component; no mypy
.github/workflows/validate.yml   hacs/action + hassfest + ruff/pytest
```

```bash
pip install -e ".[test]"      # pulls HA; needs a POSIX host (use WSL on Windows)
ruff check . && pytest        # both green before committing (CI runs them too)
```

Dev install: copy `custom_components/homapel_insights/` into HA's `config/custom_components/`, restart, add the integration. End-to-end check: bring up `laris_insights` against the shared Postgres, add the integration with a real unit key, call the `homapel_insights.upload_test_signal` service, run the cloud synth worker, call it again → a notification appears.

---

## 5. Conventions & hard gates

1. **Tests for new analysis logic** (keep `analysis/` HA-free so it stays testable without an HA runtime); `ruff check .` and `pytest` green before committing.
2. **Never commit straight to `main`.** Feature branch → PR → `main`.
3. **Every user-visible string in TR and EN** (`strings.json` + `translations/{en,tr}.json`), notification buttons included — they come from the `common` section, not from literals in `delivery.py`. hassfest validates `strings.json` **and** `translations/en.json`: no HTML, no bare URLs (use a placeholder).
4. **Never upload anything the customer didn't opt in to**; the opt-in gate in `__init__.py` must stay the first check.
5. **No third-party requirements** in `manifest.json`.
6. Product is Laris; the manifest `name` still says "Homapel Insights" and the directory says `homapel_insights` — cosmetic, don't rename without being asked.

---

## 6. Gotchas

- `manifest.json` `issue_tracker`/`documentation` point at `github.com/homapel/homapel_insights` / `homapel.com` — make sure they match the repo customers actually install from before a HACS store submission.
- Validating a key means talking to `agentic_service` (`/v1/units/status`), not to `laris_insights` — the ingest API has no validation endpoint, so an entry carries two endpoints: `cloud_base_url` (uploads) and `voice_api_base` (key checks).
- `proactive_service/PROACTIVE_INSIGHTS_PLAN.md` describes edge-side deterministic analyzers producing verdicts; the shipped design ships observation windows and lets the cloud decide. Where they disagree, the code wins.
