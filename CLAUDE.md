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
is only carried along. **All development happens in the nine `social_media_*` modules**,
which are tracked on the fork branch `17.0-add-social_media`. A `git status` touching
anything else means an upstream addon was modified by mistake.

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

### Where the network-specific constants live

Every module keeps its endpoints, limits, scopes, URNs and mimetypes in a **top-level
`social_<name>_utils.py`** (`social_media_linkedin/social_linkedin_utils.py`,
`social_media_x/social_x_utils.py`,
`social_media_linkedin_sync/social_linkedin_sync_utils.py`,
`social_media_advertising/social_advertising_utils.py`,
`social_media_advertising_linkedin/social_advertising_linkedin_utils.py`), never inline
in the models. Names are `_UPPER_CASE_<NETWORK>` — the network suffix is what keeps two
connectors' constants apart once both are imported. A new limit, endpoint or page size
goes there, not next to the code that uses it.

### How the network is reached

Every connector funnels its HTTP through a single entry point on `social.account`, and
that entry point is where an authentication failure becomes a `SocialCredentialsError`.
LinkedIn has `_request_linkedin()` (`social_media_linkedin/models/social_account.py`),
used by the sync and advertising bridges too; X builds the `tweepy.Client` /
`tweepy.API` in one builder and maps `Unauthorized` / `Forbidden` / `TooManyRequests`
there. A new call goes through the funnel instead of calling `requests` or `tweepy`
directly — it is also the seam the tests patch
(`PATCH_ACCOUNT_LINKEDIN.format("_request_linkedin")`).

### Install hooks

`social_media_base/hooks.py` exposes `remove_social_media(env, media_type)`; each
connector's `uninstall_hook` calls it so uninstalling drops its `social.media` record
(otherwise the row survives with a `media_type` no longer in the selection).
`post_init_hook` is used the other way around, to tell the user something the code
cannot fix by itself — `social_media_linkedin_sync` and
`social_media_advertising_linkedin` post on the chatter of the affected accounts that
the widened OAuth scopes need a fresh authorization.

### Comments and reactions (`social_media_sync`)

The chatter of a `social.post.account` is not a chatter:
`social_media_sync/controllers/thread.py` overrides `/mail/message/post` so that, for
that model, the message is published on the network through `create_comment()` instead
of being stored as a `mail.message`, and the result is pushed to the author's partner
channel with the bus type `comments` (the payload carries `post_account_id` because
every open dialog listens on the same partner channel). Nothing is mirrored into Odoo —
reading a thread is `get_comments()` / `get_comment_replies(comment_ref)` against the
network each time.

Connector hooks on `social.post.account` (empty in `social_media_sync`, filled by
`social_media_linkedin_sync` / `social_media_x_sync`): `get_comments`,
`get_comment_replies`, `create_comment`, `action_like_post` / `action_unlike_post`,
`action_like_comment` / `action_unlike_comment`, `_check_remote_post_exists`. A
connector whose API returns the whole thread nested leaves `get_comment_replies`
unimplemented. When an action reveals the publication is gone, the answer carries
`post_deleted` and `_register_remote_post_gone()` marks the line `deleted`.

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
   client-side, so anything not already `Markup` is escaped. The callbacks are
   `/linkedin/callback` and `/social_x/callback` (`auth="user"`), and they are the only
   code that sets `social_media_oauth_callback` in the context.
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

`static/src/` in every module: OWL components under `components/`, services under
`js/services/`, views under `js/views/`, shared behaviour under `js/app/`. Files use the
`.esm.js` suffix and the `/** @odoo-module */` header. Connectors extend by adding files
under the same globs in their own manifest `assets`.

Registry names in use, with the module that registers them:

| Category | Name                                                                                         | Module        |
| -------- | -------------------------------------------------------------------------------------------- | ------------- |
| views    | `social_kanban`                                                                              | base          |
| views    | `social_calendar`                                                                            | calendar      |
| views    | `social_ads_kanban`                                                                          | advertising   |
| fields   | `social_post_preview`, `social_message`, `social_media_binary`, `social_post_account_kanban` | base          |
| services | `social_media_notification` (session channel + the `social_form_*` bus types)                | base          |
| services | `social_service` (sync also patches mail's `ThreadService` prototype)                        | sync          |
| services | `social_linkedin_service`                                                                    | linkedin_sync |

Bus types consumed by the client, and who consumes them:

| Type                                                                 | Consumer                                            |
| -------------------------------------------------------------------- | --------------------------------------------------- |
| `social_form_danger`, `social_form_success`, `social_form_info`      | `social_media_notification` service                 |
| `social_kanban_danger`, `social_need_update`, `social_posts_updated` | `js/app/social_media_mixin.esm.js`                  |
| `social_ads_need_update`                                             | `social_ads_kanban_controller.esm.js` (advertising) |
| `comments`                                                           | `social_comment_dialog.esm.js` (sync)               |

The mixin composes its own danger type as
`` `social_${this.notifView ?? "kanban"}_danger` ``, so a view that sets `notifView`
listens on a different type without any server change.

SCSS order matters and is enforced by the manifest globs: `_social_mixins.scss` is
listed before the rest, because the whole bundle is compiled as one unit. Same reason
`social_media_linkedin_sync` lists `js/services/**` before `components/**`.

## Tests

Base class `odoo.addons.base.tests.common.BaseCommon` (`HttpCase` where the test needs a
web request). Each module keeps one common file with the shared `setUpClass` and the
`PATCH_*` string templates used with `unittest.mock.patch` — the name varies
(`test_social_common.py`, `test_common_linkedin.py`, `test_common_x.py`,
`test_social_sync_common.py`, `test_sync_linkedin_common.py`, `test_sync_x_common.py`,
`test_social_advertising_common.py`, `test_common_advertising_linkedin.py`), so look for
the `*common*.py` in `tests/` rather than guessing it:

```python
patch(PATCH_ACCOUNT_LINKEDIN.format("_request_linkedin"), ...)
```

**No network calls** — every HTTP call is patched. Connector tests are
`@tagged("post_install", "-at_install")`: at install time the connector's `media_type`
is not yet a legal value of the selection.

`social_media_base/tests/test_card_footer_matrix.py` is the one file tagged
`-standard, card_footer_matrix` on purpose: it asserts what an installation _without_
the sync modules draws, which the full suite can never reproduce. The bridges'
`test_card_footer_*.py` are ordinary `post_install` tests. Run the matrix one against
the install-matrix databases:

```bash
odoo -d <database> --test-enable --stop-after-init --workers=0 \
    -u social_media_base --test-tags card_footer_matrix
```

Those Python tests drive JS tours registered under `<module>/static/tests/tours/`:
`social_media_base.card_footer_matrix`, `social_media_sync.card_footer`,
`social_media_linkedin_sync.card_footer` and `social_media_x_sync.card_footer`. What the
footer draws is asserted in the tour, so a change to the card means editing the tour,
not the Python side.

## Conventions

- Odoo 17.0 Community + OCA guidelines. Code, comments and docstrings in English.
- OCA layout (`models/`, `wizards/`, `controllers/`, `security/`, `views/`, `data/`,
  `tests/`, `readme/`, `static/`) and OCA manifests: `version: "17.0.x.y.z"`,
  `license: AGPL-3`, `author: "Binhex, Odoo Community Association (OCA)"`,
  `website: https://github.com/OCA/social`, `maintainers: ["edescalona"]`.
- **The nine `social_media_*` modules stay at `version: "17.0.1.0.0"`.** None of them
  has been released yet, so there is no installed base to migrate from and nothing to
  read a bump against: a change goes in with the version untouched. The first release is
  what starts moving `x.y.z`.
- Commits for these modules belong on this repository's branch, not on the deployment
  repository, which only tracks orchestration files.

## Spec branches

Every spec is implemented on its own branch (`spec-<n>-<slug>`), branched off
`17.0-add-social_media`.

When a spec moves to `Implementado` (or any equivalent closing state), close its branch
in the same step, without being asked again:

1. `git checkout 17.0-add-social_media`.
2. Merge the spec branch into it.
3. Delete the spec branch, local and remote: `git branch -d <branch>` and
   `git push edescalona --delete <branch>`.
4. Stay on `17.0-add-social_media` — that is the branch the working tree is left on.

Pushing `17.0-add-social_media` itself stays with me, like every other commit and push.

## Publishing rules

Never publish, post, comment, or otherwise submit content to a real account without my
explicit approval in this conversation first.

Before any publishing action:

1. Show me the full text of the post or comment, plus the caption or copy that goes with
   any image or video.
2. Wait for my explicit "yes" or "approved".

## Content rules

- Published content: English only.
- Topic: technology only.
- If a draft falls outside technology, say so and propose an alternative instead of
  publishing.

## Conversation language

Always talk to me in Spanish, including when the draft itself is in English.
Explanations, questions, and suggestions: Spanish.
