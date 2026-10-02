# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in
this repository.

The deployment-level `CLAUDE.md` two directories up (`OCA_17CE/CLAUDE.md`) is loaded
too: it holds the Docker/`invoke` commands, how to run a single test, and the
`social_media_*` architecture. This file only adds what is specific to this subrepo.

## What this repository is

A fork of OCA/social, branch 17.0. Everything except the `social_media_*` addons is
upstream OCA code that is not developed here; leave the `mail_*`, `mass_mailing_*` and
other addons alone.

Remotes: `oca` (OCA/social), `binhex` (BinhexTeam/social, one
`17.0-add-social_media_<module>` branch per module), `edescalona` / `origin` (the
personal fork). The working branch is `17.0-add-social_media`.

## Branch workflow

- Each feature comes from a spec and lives on a `spec-NN-slug` branch cut from
  `17.0-add-social_media`; it is merged back with `--no-ff` and the default merge
  message (see "Closing a spec" in the deployment `CLAUDE.md`).
- Specs live outside the repo, in `~/Documents/02-WORK/05-SPECIFICATIONS/SOCIAL/`
  (`NN-slug.md`, plus `BACKLOG.md`). Never write spec documents inside this repo.
- The Binhex per-module branches are merged into `17.0-add-social_media` as
  `Merge remote-tracking branch 'binhex/17.0-add-social_media_<module>'`.

Commit subjects follow the OCA prefix form, one module per commit: `[ADD]`, `[IMP]`,
`[FIX]`, `[REF]`, `[I18N] <module>: Update translation files`, e.g.
`[FIX] social_media_x: Show the credit warnings on the bus`.

## Lint and generated files

```bash
pre-commit run --all-files                       # from this directory
pre-commit run --files social_media_x/**/*       # limit to one module
```

The hooks (OCA template v1.29, `.copier-answers.yml`) regenerate `README.rst` from
`readme/*.md`, `requirements.txt` from the manifests' `external_dependencies`, and
`pyproject.toml` (whool). Edit only the sources. `.pylintrc-mandatory` is what CI
enforces; `.pylintrc` adds the optional checks.

Never place an f-string among the arguments of `_()`: babel stops extracting the terms
that follow it in the file. Format the value apart and pass it as a `%(name)s` argument.
After touching translatable strings, check that the `.pot` diff contains every term.

## Tests

Shared fixtures form a hierarchy, each one inheriting the previous:

- `social_media_base/tests/test_social_common.py` —
  `TestSocialMediaBaseCommon(BaseCommon)` and the base `PATCH_*` templates
  (`PATCH_ACCOUNT`, `PATCH_POST_ACCOUNT`, `PATCH_MEDIA`, `PATCH_SOCIAL_BASE_MIXIN`…).
- Connectors: `social_media_linkedin/tests/test_common_linkedin.py`
  (`TestSocialCommonLinkedin`, plus `LinkedinMockMixin`),
  `social_media_x/tests/test_common_x.py` (`TestSocialCommonX`,
  `PATCH_REQUEST_GET`/`PATCH_REQUEST_POST` patch `requests` inside `social_account`).
- `social_media_sync/tests/test_social_sync_common.py`,
  `social_media_advertising/tests/test_social_advertising_common.py`.
- Glue modules extend the connector fixture: `TestSocialSyncCommonLinkedin`,
  `TestSocialSyncCommonX`, `TestSocialCommonAdvertisingLinkedin`.

Reuse the closest fixture and its `PATCH_*` strings instead of building new mocks.

## Rules specific to these modules

- **Connectors never mention each other.** `social_media_x*` code, comments, docs and
  tests never refer to LinkedIn, and vice versa; shared behaviour belongs in
  `social_media_base` / `social_media_sync`.
- **Bus types actually listened to.**
  `social_media_base/static/src/js/services/social_notification_service.esm.js`
  subscribes only to `social_form_info` and `social_form_success`; `social_need_update`
  is handled in `js/app/social_media_mixin.esm.js`. A danger notice pushed through the
  bus must travel with `bus_type="social_form_info"` (the payload's `message_type` keeps
  it red); failures from OAuth callbacks go through `_notify_user_session`.
- **`*_sync` modules stay out of the `devel` database.** Their crons call the networks
  and spend X API credits. Install them only inside test runs.
- Each connector's `hooks.py` `uninstall_hook` calls
  `social.account._remove_social_media("<media_type>")`; a new connector needs the same.
