# PHASE 0: Environment Inspection and Project Setup

Status: COMPLETE
Date: 2026-10-20
Site used: shbi.localhost
App reused: sahbi 0.0.1 (develop)

Read `SAHBI_MASTER_PROMPT.md` completely before later phases.

This phase inspects the existing environment before making product
changes. It does not implement financial business logic.

Do not assume a new installation is required.
Do not delete or recreate existing sites.
Do not modify unrelated applications.

If a Frappe application already exists for Sahbi, inspect it
and reuse it where appropriate.

---

## Scope of this phase

Determine:

- Frappe version
- Python version
- Available Bench directory
- Existing sites
- Installed applications
- MariaDB availability
- Ollama availability
- Existing application structure, if any

Report:

1. Environment details
2. Missing prerequisites
3. Recommended application location
4. Commands needed to complete setup
5. Files created or changed
6. Verification results

---

## 1. Environment details

A working Frappe bench already exists. Sahbi is already a custom app
in that bench, and it is already installed on a dedicated site.
No new bench, site, or app was created.

### Bench

- Bench directory: `/home/beshoy/SAAS/frappe-press`
- Bench CLI: 5.24.1
- Process manager: honcho (`honcho start` via Procfile)
- Web: `http://127.0.0.1:8000` (port 8000 listening)
- Default site: `shbi.localhost`
- DNS multitenant: enabled
- Host timezone: `Africa/Cairo`

### Runtime

- System Python: 3.12.3 (`/usr/bin/python3`)
- Bench virtualenv Python: 3.12.3 (`/home/beshoy/SAAS/frappe-press/env`)
- Node: v22.22.2
- npm: 10.9.7
- Redis cache: `127.0.0.1:13000` (PONG)
- Redis queue: `127.0.0.1:11000` (PONG)
- SocketIO: port 9000 listening

### Frappe and related apps in the bench

The bench contains many apps. Only Frappe and Sahbi are installed
on the Sahbi site. Do not install ERPNext, HRMS, Raven, or other
bench apps onto `shbi.localhost` unless a later phase explicitly
requires them.

- Frappe: 15.96.0 (`version-15`)
- ERPNext present in bench, not installed on `shbi.localhost`: 15.94.3
- Other bench apps (not on the Sahbi site): ecommerce_integrations,
  askary_daily, website_saas, oryntiq, expert_build,
  property_management, hrms, infinty_care, inventory_client,
  inventory_server, material_ui, site_manager, raven, sub_manager

Bench `sites/apps.txt` includes `sahbi`.

### Sahbi site

- Site: `shbi.localhost`
- Database type: MariaDB
- Installed apps on this site:
  - frappe 15.96.0 (`version-15`)
  - sahbi 0.0.1 (`develop`)
- Setup wizard: complete
- Country: Egypt
- Currency: EGP
- Time zone: Africa/Cairo
- Language: en
- Date format: dd-mm-yyyy
- Float precision: 3
- Currency precision: unset (Frappe default)
- Module Def: `Sahbi` exists
- DocTypes in module Sahbi: none
- HTTP: `http://shbi.localhost:8000` returns 200

### MariaDB

- Server: MariaDB 11.8.9 (`11.8.9-MariaDB-ubu2404`)
- Listening: `127.0.0.1:3306`
- Site connection via `bench --site shbi.localhost mariadb`: working
- OS user `beshoy` cannot log in without a password. That is expected.
  Frappe uses the site database user. Do not change MariaDB accounts.

### Ollama

- Binary: `/usr/local/bin/ollama` 0.20.7
- Service: active (`ollama serve`, pid present)
- API: `127.0.0.1:11434` listening
- Installed models:
  - `qwen2.5:1.5b` (986 MB) — matches the spec stack name
  - `medical-ar:latest` (Qwen2 1.5B fine-tune, unrelated)
  - `Aqirito/TinyLlama-1.1B-Chat-v1.0-KMSB-fine-tuned:latest`
  - `gemma4:latest`
  - `embeddinggemma:latest`

Do not call Ollama from application code in this phase.

### Existing Sahbi application structure

Path: `/home/beshoy/SAAS/frappe-press/apps/sahbi`

Git: branch `develop`, one commit `7576a3e feat: Initialize App`

This is a standard `bench new-app` scaffold. There is no financial
code, API, test package, or LLM client.

```
sahbi/
  hooks.py                 metadata only; functional hooks commented
  modules.txt              Sahbi
  patches.txt              empty pre/post sections
  __init__.py              __version__ = "0.0.1"
  sahbi/                   empty module package (DocTypes go here)
  public/                  empty
  templates/               empty
  config/                  empty
pyproject.toml             requires-python >=3.10; no extra deps
README.md                  default install notes
SAHBI_MASTER_PROMPT.md     product spec (untracked)
Phsae0.MD                  this file
```

`pyproject.toml` comments Frappe 15 as managed by bench. That matches
the installed Frappe version.

---

## 2. Missing prerequisites

Nothing blocking Phase 0. The bench, site, app, MariaDB, Redis, and
Ollama are already available.

Not missing, but not yet configured for later phases:

- No Sahbi DocTypes, Python services, or tests
- Desk language is English, not Egyptian Arabic
- Currency precision is unset
- No `developer_mode` was set on the site before this phase
- Tests were disabled on the site before this phase
- Only `qwen2.5:1.5b` is installed. That is enough to prove Ollama
  works. A larger Qwen model may be needed for Egyptian Arabic NLU
  in the LLM phase. Do not pull a new model until that phase.

Do not treat ERPNext as a Sahbi prerequisite.

---

## 3. Recommended application location

Reuse the existing app and site. Do not create another app or site.

- App: `/home/beshoy/SAAS/frappe-press/apps/sahbi`
- Frappe module folder: `/home/beshoy/SAAS/frappe-press/apps/sahbi/sahbi/sahbi/`
- Site: `shbi.localhost`
- Bench: `/home/beshoy/SAAS/frappe-press`

Commands in later phases must use:

```bash
cd /home/beshoy/SAAS/frappe-press
bench --site shbi.localhost <command>
```

---

## 4. Commands needed to complete setup

These were already done before this phase. Do not run them again.

```bash
# already exists; do not recreate
# bench new-app sahbi
# bench new-site shbi.localhost
# bench --site shbi.localhost install-app sahbi
```

Executed in this phase (Sahbi site only):

```bash
cd /home/beshoy/SAAS/frappe-press
bench --site shbi.localhost set-config developer_mode 1
bench --site shbi.localhost set-config allow_tests true
bench --site shbi.localhost clear-cache
```

Not run, and not required for Phase 0:

```bash
# ollama pull <larger-qwen>    # LLM phase only
# bench --site shbi.localhost install-app erpnext
# bench migrate                # no new DocTypes yet
```

---

## 5. Files created or changed

Inside the Sahbi app repository:

- `Phsae0.MD` — this completed Phase 0 report

Outside the app repository, Sahbi site only:

- `sites/shbi.localhost/site_config.json`
  - `developer_mode`: 1
  - `allow_tests`: true

No Python business logic, DocTypes, hooks, or dependencies were added.
Unrelated apps and sites were not modified.

---

## 6. Verification results

| Check | Result |
|---|---|
| Frappe import in bench env | 15.96.0 |
| `sahbi` import in bench env | 0.0.1 |
| `bench --site shbi.localhost list-apps` | frappe, sahbi |
| Module Def `Sahbi` | present |
| Sahbi DocTypes | none |
| MariaDB via site | 11.8.9-MariaDB-ubu2404 |
| Redis cache / queue | PONG / PONG |
| `http://shbi.localhost:8000` | HTTP 200 |
| Scheduler workers | 1 online |
| Ollama `qwen2.5:1.5b` | installed and API reachable |
| `bench --site shbi.localhost run-tests --app sahbi` | Ran 0 tests in 0.000s (NO TESTS RAN) |

Tests are enabled on the site. There are no test files yet, so zero
tests is the correct result for this phase.

---

## Phase 0 conclusion

Sahbi can be developed on the existing bench and site.

Next phase may add DocTypes and deterministic Python posting logic
under `sahbi/sahbi/`. It must not add LLM calls, chat UI, ERPNext,
or unrelated bench apps.

Remaining blockers for later phases, not for this one:

- Product decisions still open in the master prompt (channel, record
  taxonomy, incoming-money default, household/work field, phases
  after this one)
- No automated financial tests exist yet
- Qwen 1.5B may be too small for Egyptian Arabic extraction
