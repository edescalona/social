# Copyright 2026 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests.common import HttpCase, tagged

from .test_sync_x_common import TestSocialSyncCommonX

DASHBOARD_URL = "/web#action=social_media_base.social_post_account_action"


@tagged("post_install", "-at_install")
class TestUpdateNoticeX(HttpCase, TestSocialSyncCommonX):
    """What the *Update* button says after reading the timeline of X.

    The figures are refreshed over the publications of the window before the
    import runs, so an X account with nothing published lately refreshes
    nothing there even when its timeline was read right after.
    """

    def test_update_notice_x(self):
        publication = self.dashboard_publication(
            self.media_x_id, "X account of the tour", "X tour publication"
        )
        account = publication.account_id
        self.assertEqual(account.media_type, "x")
        SocialAccount = type(self.SocialAccount)
        # Nothing in the window answers, so nothing counts as refreshed there,
        # whatever the database the tour runs against holds.
        self.patch(SocialAccount, "_refresh_statistics", lambda self: False)
        self.patch(
            SocialAccount,
            "_write_posts_metrics",
            lambda self, post_accounts: post_accounts.browse(),
        )
        # The import answers with the account, as it does once X was read.
        self.patch(
            SocialAccount,
            "_update_posts_statistics",
            lambda self, post_id, domain, imported=None: [
                {"id": account.id, "name": account.name}
            ],
        )
        self.start_tour(
            DASHBOARD_URL, "social_media_x_sync.update_notice_x", login="admin"
        )
