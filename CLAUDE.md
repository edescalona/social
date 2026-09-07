# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in
this repository.

## What this repository is

A fork of [OCA/social](https://github.com/OCA/social) for Odoo 17.0, checked out by
git-aggregator as `odoo/custom/src/social_edescalona` inside the Doodba deployment two
levels up (`OCA_17CE/`, whose own `CLAUDE.md` documents the container/orchestration
layer).

Remotes: `oca` (upstream) and `edescalona`/`origin` (the fork). Working branch
`17.0-add-social_media`, aggregated as `oca 17.0` + `edescalona 17.0-add-social_media`.

Everything except `social_media_*` is upstream OCA (`mail_*`, `mass_mailing_*`, …) and
is only carried along. **All development happens in the nine `social_media_*` modules.**
They are still untracked in the working copy, so `git status` showing them as `??` is
the normal state, not a mistake.

## Commands

Odoo never runs on the host — all of it goes through the deployment root:

```bash
cd ../../../..                                      # OCA_17CE, where tasks.py lives
invoke start / restart / stop
invoke logs --tail=50
invoke install --modules social_media_base
invoke resetdb --modules social_media_base
```

Tests (the addon name is inferred from the current directory):

```bash
cd social_media_linkedin && invoke test
invoke test --modules social_media_base,social_media_linkedin
invoke test --modules social_media_x --mode update    # -u instead of -i
```

A single class or method needs Odoo directly — `invoke test` only builds `/<module>`
tags:

```bash
docker compose run --rm -e DB_FILTER='^devel$' odoo \
  odoo --test-enable --stop-after-init --workers=0 -u social_media_linkedin \
  --test-tags /social_media_linkedin:TestPostLinkedin.test_action_post
```

Odoo stays in test mode afterwards; `invoke restart` returns it to normal.

Lint runs from **this** repository, not the deployment root (that one has no
`.pre-commit-config.yaml`):

```bash
pre-commit run --all-files
```

The OCA standard set: `ruff` + `ruff-format` (isort with an `odoo` / `odoo.addons`
section order, `max-complexity = 16`), `pylint_odoo`, `oca-checks-odoo-module`,
`prettier` + `eslint`, `oca-gen-addon-readme`, `oca-gen-external-dependencies`.

**Never hand-edit a module's `README.rst`** — it is generated from
`<module>/readme/*.md` fragments (`DESCRIPTION.md`, `CONFIGURE.md`, `INSTALL.md`,
`USAGE.md`, `ROADMAP.md`, `CONTRIBUTORS.md`). Same for the repository
`requirements.txt`, generated from the manifests' `external_dependencies`.

## Module map

Three layers, each connector plugging into the generic one above it:

```
social_media_base ── social_media_calendar        (auto_install)
      ├─ social_media_linkedin ── social_media_linkedin_sync  (auto_install)
      ├─ social_media_x        ── social_media_x_sync         (auto_install)
      ├─ social_media_sync ────────────┘  (both *_sync depend on it)
      └─ social_media_advertising ── social_media_advertising_linkedin
```

The split between `social_media_base` and `social_media_sync` is a **cost line, not a
feature line**: base only ever spends a fixed number of calls per account however much
that account has published (publishing, account figures, the daily series). Anything
whose cost grows with the history of the account — importing the publications, checking
they still exist, their comments and reactions — lives in `social_media_sync` and its
two bridges. When adding a method, that question decides which module it belongs to.

`social_media_advertising` adds the ads layer (`utm` and `link_tracker` extensions
themselves live in `social_media_base`), `social_media_advertising_linkedin` implements
it for LinkedIn.

## Core models

- `social.media` — one record per supported network. `media_type` is an **empty
  `Selection` extended by each connector** through `selection_add`; connectors also
  override `action_open_account()` (returns their own association wizard) and
  `_get_utm_medium()`.
- `social.account` — a linked account. Holds `remote_ref`, OAuth credentials
  (`access_token` / `refresh_access_token`, restricted to `base.group_system`),
  aggregated counters and `user_id` (responsible). Inherits `mail.thread`,
  `mail.activity.mixin`, `avatar.mixin`, `social.media.base.mixin`,
  `social.statistics.mixin`.
- `social.post` — the editorial content, state
  `draft → planned → publishing → published / cancelled / failed`. Fans out into one
  `social.post.account` per selected account.
- `social.post.account` — the publication on one account: its `remote_ref`, its own
  state (`ready / posted / failed / deleted`) and the figures the network reports for
  it.
- `social.account.statistics` — the daily series, one row per `(account_id, date)`.
- `wizard.social.account` — the association wizard; each connector inherits it for its
  own OAuth flow.

Mixins:

- `social.media.base.mixin` — user notifications (see below).
- `social.post.mixin` — image/video URL computation shared by posts and publications.
- `social.statistics.mixin` — `comment_count` / `like_count` / `click_count` /
  `share_count` / `impression_count` and their sum. A connector counting something else
  (X: retweets, quotes) extends **the mixin**, not each model, and overrides
  `_interaction_count_fields()`.

## Connector contract

Empty hooks in `social_media_base` that a connector fills:

| Method                                                | On                    | Purpose                                                                                                      |
| ----------------------------------------------------- | --------------------- | ------------------------------------------------------------------------------------------------------------ |
| `social.media.action_open_account`                    | `social.media`        | return the association wizard action                                                                         |
| `_action_post(post_id)`                               | `social.post.account` | publish on the network                                                                                       |
| `validate_access_token`                               | `social.account`      | cheap token check from stored dates; `check_remote_token` in the context means the user asked for a real one |
| `_refresh_credentials`                                | `social.account`      | renew the token                                                                                              |
| `_snapshot_statistics(date_from, date_to)`            | `social.account`      | write daily rows, only if the API reports per-day figures                                                    |
| `_refresh_statistics` / `_backfill_statistics(force)` | `social.account`      | rewrite the last days / fill the series as far back as the API goes                                          |
| `_on_account_associated`                              | `social.account`      | base refreshes figures and backfills; `social_media_sync` extends it to queue the import                     |
| `_run_check_media_updates`                            | `social.account`      | periodic check                                                                                               |

`_write_statistics_rows()` is the **only** place the series is written (it does the
upsert the `unique (account_id, date)` constraint needs, in `sudo()`); connectors hand
it `{date: {field: value}}`.

Advertising adds its own set on `social.account`: `_advertising_media_types`,
`_fetch_advertising_accounts`, `_fetch_ads`, `_fetch_ad_refs`,
`action_import_campaigns`. The generic side (`_sync_advertising_accounts`, `_sync_ads`,
`_check_ads_updates`, `_autoselect_advertising_account`) stays in
`social_media_advertising`.

Post previews are resolved by convention: `social.post._render_template_preview()` looks
up `social_media_{media_type}.social_media_post_preview`, so a connector only has to
declare that XML id.

## Rules that are easy to break

1. **Publication isolation.** Connectors wrap their per-account loop in
   `social.post.account._publish_guard()`, a savepoint context manager. Publishing is an
   irreversible external effect: a failure on one account must not roll back the
   `remote_ref` another one already obtained. `psycopg2.OperationalError` with a pgcode
   in `PG_CONCURRENCY_ERRORS_TO_RETRY` is re-raised on purpose so Odoo's retry still
   works; anything else is recorded as `failed` on that line via
   `_register_publish_failure`.
2. **Two notification channels, not interchangeable.** `_notify_user_client()` pushes
   through `bus.bus`. OAuth callbacks answer with a redirect that reloads the web
   client, so a bus message would race with it — those use `_notify_user_session()`,
   stashed in the session and delivered by `ir.http.session_info`. Code reached from
   both calls `_notify_user()`, which picks the session when the context carries
   `social_media_oauth_callback` and the bus otherwise. Messages render as markup
   client-side, so anything not already `Markup` is escaped.
3. **`SocialCredentialsError`** (`social_media_base/exceptions.py`) is the only failure
   worth retrying on the spot — refreshing the token may be all it takes. Everything the
   network refuses about the content itself is not.
4. **LinkedIn API versioning** is in the `LinkedIn-Version` header, not the URL: moving
   the connector to a newer API version is changing `_VERSION_STRING_LINKEDIN` in
   `social_media_linkedin/social_linkedin_utils.py`. OAuth scopes live in
   `_SCOPE_LINKEDIN` there, extended per module through
   `social.media._get_linkedin_scopes()`; a refreshed token keeps the scopes it was
   issued with, so widening the list only reaches accounts authorized again from scratch
   (hence `social_media_linkedin_sync`'s `post_init_hook`, which posts instructions on
   the chatter of the affected accounts).
5. **Advertising mirrors the network and is never pushed back.** Ads that disappear are
   archived, not deleted, and every figure carries its `statistics_date_from` /
   `statistics_date_to` window. Network statuses are `social.stage` **data per
   connector** rather than a hardcoded selection (`code` is the value the network
   returns; `stage_id` domains require record and stage to share `media_id`). Only
   cross-platform fields belong in the generic models.

## Crons

| Module      | Schedule | Code                                                                                                      |
| ----------- | -------- | --------------------------------------------------------------------------------------------------------- |
| base        | 5 min    | `social.post._run_send_post()`                                                                            |
| base        | 2 h      | `social.account._run_check_media_updates()`                                                               |
| sync        | 1 month  | `social.account._run_initial_sync()`                                                                      |
| sync        | 1 week   | `social.account._run_full_resync()` — the only pass that notices remote deletions, and the most expensive |
| advertising | 6 h      | `social.account._run_check_ads_updates()`                                                                 |

## Security

`group_social_media_user` ("User: Own Accounts") and `group_social_media_manager`
("Administrator", implies user). Records are scoped by `user_id`: a user sees their own,
a manager sees all. `can_manage_account` / `is_property_account` are computed with
`@api.depends_context("uid")`.

## Frontend

`social_media_base/static/src/`: OWL components under `components/`, services under
`js/services/`, views under `js/views/`. Files use the `.esm.js` suffix and the
`/** @odoo-module */` header. Connectors extend by adding files under the same globs in
their own manifest `assets`.

Registry names in use: views `social_form`, `social_kanban`, `social_calendar`,
`social_ads_kanban`; fields `social_post_preview`, `social_message`,
`social_media_binary`; services `social_media_notification` (drains the messages the
session channel left), `social_service`, `social_linkedin_service`.

Bus types consumed by the client: `social_kanban_danger`, `social_form_success`,
`social_form_info`, `social_need_update`, `social_ads_need_update`.

SCSS order matters and is enforced by the manifest globs: `_social_mixins.scss` is
listed before the rest, because the whole bundle is compiled as one unit. Same reason
`social_media_linkedin_sync` lists `js/services/**` before `components/**`.

## Tests

Base class `odoo.addons.base.tests.common.BaseCommon` (`HttpCase` for tours). Each
module keeps a `tests/test_*_common.py` with the shared `setUpClass` and the `PATCH_*`
string templates used with `unittest.mock.patch`:

```python
patch(PATCH_ACCOUNT_LINKEDIN.format("_request_linkedin"), ...)
```

**No network calls** — every HTTP call is patched. Connector tests are
`@tagged("post_install", "-at_install")`: at install time the connector's `media_type`
is not yet a legal value of the selection.

`test_card_footer_matrix.py` (and the `test_card_footer_*.py` of the bridges) are tagged
`-standard, card_footer_matrix` on purpose: they assert what an installation _without_
the matching sync module draws, which the full suite can never reproduce. Run them
against the install-matrix databases:

```bash
odoo -d <database> --test-enable --stop-after-init --workers=0 \
    -u social_media_base --test-tags card_footer_matrix
```

## Conventions

- Odoo 17.0 Community + OCA guidelines. Code, comments and docstrings in English.
- OCA layout (`models/`, `wizards/`, `controllers/`, `security/`, `views/`, `data/`,
  `tests/`, `readme/`, `static/`) and OCA manifests: `version: "17.0.x.y.z"`,
  `license: AGPL-3`, `author: "Binhex, Odoo Community Association (OCA)"`,
  `website: https://github.com/OCA/social`, `maintainers: ["edescalona"]`.
- Commits for these modules belong on this repository's branch, not on the deployment
  repository, which only tracks orchestration files.
