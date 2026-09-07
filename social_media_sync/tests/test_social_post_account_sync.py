# Copyright 2026 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import datetime
from unittest.mock import patch

import pytz
from freezegun import freeze_time

from odoo.tests.common import tagged
from odoo.tools import mute_logger

from .test_social_sync_common import (
    PATCH_SYNC_POST_ACCOUNT,
    TestSocialMediaSyncCommon,
)

LOGGER_SYNC_POST_ACCOUNT = "odoo.addons.social_media_sync.models.social_post_account"


@tagged("post_install", "-at_install")
class TestSocialPostAccountSync(TestSocialMediaSyncCommon):
    def test_statistics_views_show_the_imported_figures(self):
        """The figures this module imports are read from the publication.

        The three views of a publication draw them only with this module
        installed, so what is checked is the arch after the inheritance.
        """
        figures = (
            "impression_count",
            "click_count",
            "share_count",
            "like_count",
            "comment_count",
            "interactions_count",
            "engagement",
        )
        for xml_id, view_type in (
            ("social_post_account_view_form_statistics", "form"),
            ("social_post_account_view_form", "form"),
            ("social_post_account_view_tree", "tree"),
        ):
            view = self.env.ref(f"social_media_base.{xml_id}")
            arch = self.env["social.post.account"].get_view(view.id, view_type)["arch"]
            for field_name in figures:
                with self.subTest(view=xml_id, field=field_name):
                    self.assertIn(f'name="{field_name}"', arch)

    def test_statistics_dialog_tells_the_two_click_numbers_apart(self):
        """Both counters are read there, and neither is called just Clicks."""
        view = self.env.ref(
            "social_media_base.social_post_account_view_form_statistics"
        )
        arch = self.env["social.post.account"].get_view(view.id, "form")["arch"]
        self.assertLess(
            arch.index('name="link_click_count"'),
            arch.index('name="click_count"'),
            msg="The clicks Odoo counted come before the ones of the media.",
        )
        self.assertIn("Tracked Clicks", arch)
        self.assertIn("Social Media Clicks", arch)

    def test_comments(self):
        result = self.social_post_account_id.create_comment({})
        self.assertIsNone(result)

        result = self.social_post_account_id.get_comments()
        self.assertIsInstance(result, dict)
        self.assertEqual(result, {"success": False, "data": []})

    def test_get_comment_replies(self):
        """Without a connector answering, a comment has no replies to draw."""
        result = self.social_post_account_id.get_comment_replies(
            "urn:li:comment:(urn:li:activity:6666,1)"
        )
        self.assertEqual(result, {"success": False, "data": [], "count": 0})

    def test_the_connectors_do_not_rewrite_a_foreign_answer(self):
        """What the chain says about another social media travels back whole.

        Every connector extends these three hooks and answers only for its own
        ``media_type``, so a publication none of them serves is told exactly
        what this module has to say — ``success`` and ``message`` included, not
        just ``data``. The answer asserted is one no connector builds, so a
        link rewriting it is seen even when the shape it writes back matches
        the default of the hook.
        """
        answer = {
            "success": False,
            "message": "Only the media of the publication answers.",
            "data": [{"id": "foreign"}],
            "count": 0,
        }
        for hook, args in (
            ("get_comments", ()),
            ("get_comment_replies", ("urn:li:comment:(urn:li:activity:6666,1)",)),
            ("create_comment", ({"body": "Test Comment"},)),
        ):
            with (
                self.subTest(hook=hook),
                patch(PATCH_SYNC_POST_ACCOUNT.format(hook), return_value=answer),
            ):
                self.assertEqual(
                    getattr(self.social_post_account_id, hook)(*args),
                    answer,
                    msg=f"{hook} rewrote what another social media answered.",
                )

    @freeze_time("2025-05-30 12:00:00")
    def test_format_published_time_says_how_long_ago(self):
        """The moment arrives from the API in epoch milliseconds, in UTC."""
        published = datetime(2025, 5, 27, 12, 0, 0, tzinfo=pytz.utc)
        self.assertEqual(
            self.social_post_account_id._format_published_time(
                published.timestamp() * 1000
            ),
            "3 days ago",
        )

    @freeze_time("2025-05-30 12:00:00")
    def test_format_published_time_gives_one_unit(self):
        """Babel answers the largest unit that fits, never two of them."""
        published = datetime(2023, 2, 28, 12, 0, 0, tzinfo=pytz.utc)
        self.assertEqual(
            self.social_post_account_id._format_published_time(
                published.timestamp() * 1000
            ),
            "2 years ago",
        )

    def test_action_like_comment(self):
        result = self.SocialPostAccount.action_like_comment()
        self.assertEqual(
            result,
            {"success": True, "message": "", "post_deleted": False, "liked": True},
        )

    def test_action_unlike_hooks(self):
        """Withdrawing a reaction is a hook of its own, and answers the same."""
        self.assertEqual(
            self.SocialPostAccount.action_unlike_comment(),
            {"success": True, "message": "", "post_deleted": False, "liked": False},
        )
        self.assertEqual(
            self.SocialPostAccount.action_unlike_post(),
            {"success": True, "message": "", "post_deleted": False, "liked": False},
        )

    def test_action_open_post_account_url_gone(self):
        """A publication gone from the social media is not opened."""
        post_account = self.social_post_account_id
        post_account.write(
            {
                "post_account_url": "https://example.test/post/1",
                "remote_ref": "urn:li:share:gone",
                "state": "posted",
            }
        )
        with patch.object(
            type(post_account), "_check_remote_post_exists", return_value=False
        ):
            action = post_account.action_open_post_account_url()
        self.assertEqual(action["tag"], "display_notification")
        self.assertEqual(action["params"]["type"], "warning")
        self.assertEqual(action["params"]["next"]["tag"], "reload")

    def test_check_post_exists_without_remote_ref(self):
        """Without a remote reference there is nothing to look for."""
        post_account = self.social_post_account_id
        post_account.write({"remote_ref": False})
        self.assertFalse(post_account.check_post_exists())

    def test_remote_post_gone_on_action(self):
        """The publication is asked about before an action marks it gone."""
        post_account = self.social_post_account_id
        with patch.object(
            type(post_account), "_check_remote_post_exists", return_value=False
        ):
            self.assertTrue(post_account._remote_post_gone_on_action())
        with patch.object(
            type(post_account), "_check_remote_post_exists", return_value=True
        ):
            self.assertFalse(post_account._remote_post_gone_on_action())

    @mute_logger(LOGGER_SYNC_POST_ACCOUNT)
    def test_remote_post_gone_on_action_unreachable(self):
        """A check that fails answers no deletion instead of raising."""
        post_account = self.social_post_account_id
        with patch.object(
            type(post_account),
            "_check_remote_post_exists",
            side_effect=ValueError("unreachable"),
        ):
            self.assertFalse(post_account._remote_post_gone_on_action())

    def test_register_remote_post_gone_keeps_the_reference(self):
        """The reference survives the deletion: detection is not infallible."""
        post_account = self.social_post_account_id
        post_account.write(
            {
                "remote_ref": "urn:li:share:kept",
                "post_account_url": "https://example.test/post/1",
                "state": "posted",
            }
        )
        post_account._register_remote_post_gone()
        self.assertEqual(post_account.state, "deleted")
        self.assertFalse(post_account.post_account_url)
        self.assertEqual(post_account.remote_ref, "urn:li:share:kept")
