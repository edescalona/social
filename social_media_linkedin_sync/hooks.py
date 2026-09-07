# Copyright 2026 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import _

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Tell the LinkedIn accounts that their token cannot read the history.

    An access token keeps the scopes it was issued with, so every account
    associated before this module was installed reaches the import without
    ``r_organization_social`` and LinkedIn refuses the call. Nothing can be
    fixed from here: only a new authorization brings the scope, and it needs
    the matching product on the LinkedIn application first. The accounts are
    posted the instructions instead, on their own chatter, so the message is
    waiting for whoever opens them.

    This module installs on its own together with ``social_media_sync``, so
    nobody decides to install it and nobody goes looking for what changed.
    """
    accounts = env["social.account"].search([("media_id.media_type", "=", "linkedin")])
    concerned = accounts.filtered(lambda account: account.linkedin_missing_sync_scopes)
    if not concerned:
        return
    _logger.info(
        "%d LinkedIn account(s) have to be authorized again to import their history",
        len(concerned),
    )
    for account in concerned:
        account.message_post(
            body=_(
                "The import of the LinkedIn history was installed. The token "
                "of this account was not granted %(scopes)s, so LinkedIn "
                "refuses to serve its publications. Enable the matching "
                "product on the LinkedIn application, then press Update "
                "account with Update keys checked to authorize this account "
                "again: refreshing the token alone keeps the scopes it "
                "already has.",
                scopes=account.linkedin_missing_sync_scopes,
            )
        )
