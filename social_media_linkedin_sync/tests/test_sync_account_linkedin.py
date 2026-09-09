# Copyright 2026 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import MagicMock, patch
from urllib.parse import quote

from dateutil.relativedelta import relativedelta

from odoo import _
from odoo.exceptions import UserError
from odoo.tools import mute_logger

from odoo.addons.social_media_linkedin.social_linkedin_utils import (
    _POSTS_MAX_PAGES_LINKEDIN,
    _QUERY_STRING_MAX_BYTES_LINKEDIN,
    linkedin_reaction_id,
    social_url_encode,
)
from odoo.addons.social_media_linkedin.tests.test_common_linkedin import (
    PATCH_ACCOUNT_LINKEDIN,
    RECENT_STATISTICS_LINKEDIN,
)

from .test_sync_linkedin_common import (
    PATCH_SYNC_ACCOUNT_LINKEDIN,
    PATCH_SYNC_POST_ACCOUNT_LINKEDIN,
    TestSocialSyncCommonLinkedin,
)

LOGGER_ACCOUNT_LINKEDIN = "odoo.addons.social_media_linkedin.models.social_account"
LOGGER_ACCOUNT_SYNC_LINKEDIN = (
    "odoo.addons.social_media_linkedin_sync.models.social_account"
)


class TestSocialSyncAccountLinkedin(TestSocialSyncCommonLinkedin):
    """Importing the publications of a LinkedIn page and their statistics."""

    def test_get_all_posts_walks_every_page(self):
        """The feed is read until a page comes back empty."""
        pages = [
            [{"id": f"urn:li:share:{index}"} for index in range(3)],
            [{"id": "urn:li:share:3"}],
            [],
        ]
        with patch.object(
            type(self.SocialAccountLinkedin), "_get_posts", side_effect=pages
        ) as mock_get_posts:
            posts, complete = self.SocialAccountLinkedin._get_all_posts()
        self.assertTrue(complete)
        self.assertEqual(len(posts), 4)
        self.assertEqual(mock_get_posts.call_count, 3)
        starts = [
            call.kwargs["params_values"]["start"]
            for call in mock_get_posts.call_args_list
        ]
        self.assertEqual(starts, [0, 100, 200])

    def test_get_all_posts_keeps_reading_after_a_short_page(self):
        """A page shorter than asked is not the end of the feed."""
        pages = [[{"id": "urn:li:share:1"}], [{"id": "urn:li:share:2"}], []]
        with patch.object(
            type(self.SocialAccountLinkedin), "_get_posts", side_effect=pages
        ):
            posts, complete = self.SocialAccountLinkedin._get_all_posts()
        self.assertTrue(complete)
        self.assertEqual(
            [post["id"] for post in posts], ["urn:li:share:1", "urn:li:share:2"]
        )

    @mute_logger(LOGGER_ACCOUNT_LINKEDIN, LOGGER_ACCOUNT_SYNC_LINKEDIN)
    def test_get_all_posts_stops_at_the_page_cap(self):
        """A feed longer than the cap is reported as read partially."""
        with patch.object(
            type(self.SocialAccountLinkedin),
            "_get_posts",
            return_value=[{"id": "urn:li:share:1"}],
        ) as mock_get_posts:
            posts, complete = self.SocialAccountLinkedin._get_all_posts()
        self.assertFalse(complete)
        self.assertEqual(mock_get_posts.call_count, _POSTS_MAX_PAGES_LINKEDIN)
        self.assertEqual(len(posts), 1)

    @mute_logger(LOGGER_ACCOUNT_LINKEDIN, LOGGER_ACCOUNT_SYNC_LINKEDIN)
    def test_get_linkedin_images_download_url_error_is_not_fatal(self):
        """A failure reading the images does not stop the statistics pass."""
        mock_response = self.generate_magic_mock(**{"status_code": 403})
        with self.get_patch_exceptions_linkedin(mock_response):
            urls = self.SocialAccountLinkedin._get_linkedin_images_download_url(
                ["urn:li:image:1"]
            )
        self.assertEqual(urls, {})
        self.assertEqual(
            self.SocialAccountLinkedin._get_linkedin_images_download_url([]), {}
        )

    def test_update_posts_statistics_single_post_preserves_urns(self):
        ugc_posts = [
            {
                "id": "urn:li:share:new",
                "commentary": "Single post",
                "content": {"media": {"id": "urn:li:video:1"}},
                "publishedAt": 1735689600000,
                "author": "urn:li:organization:123456",
            }
        ]
        (
            patch_validate,
            patch_get_posts,
            patch_all_posts,
            patch_entity,
            patch_assets,
            patch_page,
            patch_reactions,
        ) = self._generate_update_posts_statistics_patches(ugc_posts)
        self.SocialAccountLinkedin.linkedin_statistics_checkpoint = "untouched"
        with patch_validate, patch_get_posts as mock_get_posts, patch_all_posts, (
            patch_entity
        ), patch_assets, patch_page as mock_page, patch_reactions:
            self.SocialAccountLinkedin._update_posts_statistics(
                "urn:li:share:new", None
            )
            mock_get_posts.assert_called_once()
            self.assertEqual(
                mock_get_posts.call_args.kwargs.get("params_fields"), ["ids"]
            )
            mock_page.assert_not_called()
        self.assertEqual(
            self.SocialAccountLinkedin.linkedin_statistics_checkpoint,
            "untouched",
            msg="Refreshing one publication says nothing about the page.",
        )
        self.assertEqual(self.SocialPostAccountLinkedin.remote_ref, "1234567890")
        post_account = self.SocialPostAccount.search(
            [("remote_ref", "=", "urn:li:share:new")]
        )
        self.assertTrue(post_account)
        self.assertEqual(post_account.message, "Single post")
        self.assertEqual(post_account.actor_urn, "urn:li:organization:123456")
        self.assertTrue(
            post_account.has_video,
            msg="A post whose media is a video URN is marked as a video post.",
        )

    def test_update_posts_statistics_single_post_keeps_the_account_totals(self):
        """Refreshing one post must not turn its figures into the totals."""
        account = self.SocialAccountLinkedin
        account.write(
            {
                "click_count": 5,
                "like_count": 17,
                "comment_count": 3,
                "share_count": 2,
                "impression_count": 346,
            }
        )
        ugc_posts = [
            {
                "id": "urn:li:share:new",
                "commentary": "Single post",
                "content": {},
                "publishedAt": 1735689600000,
                "author": "urn:li:organization:123456",
            }
        ]
        (
            patch_validate,
            patch_get_posts,
            patch_all_posts,
            __,
            patch_assets,
            patch_page,
            patch_reactions,
        ) = self._generate_update_posts_statistics_patches(ugc_posts)
        patch_entity = self.generate_patch(
            **{
                "model_patch": PATCH_SYNC_ACCOUNT_LINKEDIN.format(
                    "_get_entity_statistics"
                ),
                "return_value": {"urn:li:share:new": (0, 1, 0, 0, 0, 0)},
            }
        )
        with patch_validate, patch_get_posts, patch_all_posts, patch_entity, (
            patch_assets
        ), patch_page, patch_reactions:
            account._update_posts_statistics("urn:li:share:new", None)
        self.assertEqual(account.like_count, 17)
        self.assertEqual(account.impression_count, 346)
        self.assertAlmostEqual(
            account.engagement,
            27 / 346,
            places=4,
            msg="The rate is derived from the counters that were left alone.",
        )
        self.assertEqual(
            self.SocialPostAccount.search(
                [("remote_ref", "=", "urn:li:share:new")]
            ).like_count,
            1,
        )

    def test_import_stores_the_reference_of_every_downloaded_media(self):
        """The keys of ``media_refs`` are the identifiers of the images.

        Both are written in the same operation, so an imported publication
        can never end up with images the sweep of the deleted ones does not
        recognise.
        """
        account = self.SocialAccountLinkedin
        ugc_posts = [
            {
                "id": "urn:li:share:imported",
                "commentary": "Imported with an image",
                "content": {"media": {"id": "urn:li:image:imported"}},
                "publishedAt": 1735689600000,
                "author": "urn:li:organization:123456",
            }
        ]
        (
            patch_validate,
            patch_get_posts,
            patch_all_posts,
            patch_entity,
            __,
            patch_page,
            patch_reactions,
        ) = self._generate_update_posts_statistics_patches(ugc_posts)
        downloaded = self.env["ir.attachment"].create(
            {
                "name": "urn:li:image:imported",
                "type": "binary",
                "datas": self.image_base64,
            }
        )
        patch_assets = self.generate_patch(
            **{
                "model_patch": PATCH_SYNC_POST_ACCOUNT_LINKEDIN.format(
                    "_get_assets_save"
                ),
                "side_effect": lambda self, *args, **kwargs: (
                    downloaded,
                    {str(downloaded.id): "urn:li:image:imported"},
                ),
            }
        )
        with patch_validate, patch_get_posts, patch_all_posts, patch_entity, (
            patch_assets
        ), patch_page, patch_reactions:
            account._update_posts_statistics(None, None)
        imported = self.SocialPostAccount.search(
            [("remote_ref", "=", "urn:li:share:imported")]
        )
        self.assertEqual(imported.image_ids, downloaded)
        imported.invalidate_recordset(["media_refs"])
        self.assertEqual(
            imported.media_refs, {str(downloaded.id): "urn:li:image:imported"}
        )
        self.assertEqual(
            set(imported.media_refs),
            {str(image.id) for image in imported.image_ids},
            "A key that is not an image of the publication is a reference "
            "nothing can act on",
        )

    def test_update_posts_statistics_full_list_leaves_the_account_alone(self):
        """Even the whole feed writes rows and not the figures of the account.

        The daily series is what the card is drawn from, and it holds the
        figures of the whole page instead of only what Odoo imported. An
        import that wrote its own sum on top would answer the narrower
        population, and would do it last.
        """
        account = self.SocialAccountLinkedin
        account.write({"like_count": 17, "impression_count": 346})
        ugc_posts = [
            {
                "id": "urn:li:share:new",
                "commentary": "Single post",
                "content": {},
                "publishedAt": 1735689600000,
                "author": "urn:li:organization:123456",
            }
        ]
        (
            patch_validate,
            patch_get_posts,
            patch_all_posts,
            __,
            patch_assets,
            patch_page,
            patch_reactions,
        ) = self._generate_update_posts_statistics_patches(ugc_posts)
        patch_entity = self.generate_patch(
            **{
                "model_patch": PATCH_SYNC_ACCOUNT_LINKEDIN.format(
                    "_get_entity_statistics"
                ),
                "return_value": {"urn:li:share:new": (0, 1, 0, 0, 0, 12)},
            }
        )
        with patch_validate, patch_get_posts, patch_all_posts, patch_entity, (
            patch_assets
        ), patch_page, patch_reactions:
            account._update_posts_statistics(False, None)
        self.assertEqual(account.like_count, 17)
        self.assertEqual(account.impression_count, 346)
        self.assertEqual(
            self.SocialPostAccount.search(
                [("remote_ref", "=", "urn:li:share:new")]
            ).impression_count,
            12,
            msg="The figures of the publication are still written on it.",
        )

    def test_update_posts_statistics_imports_only_its_own_accounts(self):
        """A mixed recordset hands the import the LinkedIn accounts alone.

        The feed is read one account at a time, so an account of another
        social media travelling in the same recordset would be asked to
        LinkedIn for a publication list that is not there.
        """
        mixed = self.SocialAccountLinkedin | self.social_account_id
        with patch.object(
            type(self.SocialAccount),
            "_import_linkedin_posts",
            autospec=True,
        ) as mock_import:
            mixed._update_posts_statistics(False, None)
        self.assertEqual(
            [call.args[0] for call in mock_import.call_args_list],
            [self.SocialAccountLinkedin],
        )

    def test_update_posts_statistics_reports_the_account_it_imported(self):
        """The import says which accounts it read, not only what it found.

        The figures come back the same whether the feed was read or the guard
        swallowed a refusal, so the caller that clears the pending first
        import has nothing else to go by.
        """
        reported = set()
        with patch.object(
            type(self.SocialAccount),
            "_import_linkedin_posts",
            autospec=True,
        ):
            self.SocialAccountLinkedin._update_posts_statistics(False, None, reported)
        self.assertEqual(reported, set(self.SocialAccountLinkedin.ids))

    @mute_logger(LOGGER_ACCOUNT_LINKEDIN, LOGGER_ACCOUNT_SYNC_LINKEDIN)
    def test_update_posts_statistics_does_not_report_a_refused_account(self):
        """An account the guard rolled back was not imported.

        ``_statistics_guard`` keeps a refusal from stopping the accounts still
        to read, and by doing so it also keeps the caller from noticing: the
        account is left out of what the import reports.
        """
        reported = set()
        with patch.object(
            type(self.SocialAccount),
            "_import_linkedin_posts",
            autospec=True,
            side_effect=UserError(_("LinkedIn refused the feed")),
        ):
            self.SocialAccountLinkedin._update_posts_statistics(False, None, reported)
        self.assertFalse(reported)

    def test_update_posts_statistics_marks_the_page(self):
        """The import leaves the figures the check for updates compares with."""
        account = self.SocialAccountLinkedin
        account.write(
            {
                "linkedin_statistics_checkpoint": "stale",
                "posts_need_import": True,
            }
        )
        ugc_posts = [
            {
                "id": "urn:li:share:new",
                "commentary": "Single post",
                "content": {},
                "publishedAt": 1735689600000,
                "author": "urn:li:organization:123456",
            }
        ]
        (
            patch_validate,
            patch_get_posts,
            patch_all_posts,
            patch_entity,
            patch_assets,
            patch_page,
            patch_reactions,
        ) = self._generate_update_posts_statistics_patches(ugc_posts)
        with patch_validate, patch_get_posts, patch_all_posts, patch_entity, (
            patch_assets
        ), patch_page, patch_reactions:
            account._update_posts_statistics(False, None)
        self.assertEqual(
            account.linkedin_statistics_checkpoint,
            account._linkedin_statistics_checkpoint(RECENT_STATISTICS_LINKEDIN),
        )
        self.assertFalse(account.posts_need_import)

    def test_full_resync_cleans_stale_urns(self):
        """A publication gone from a feed read whole is marked as deleted."""
        remote_ref = self.SocialPostAccountLinkedin.remote_ref
        ugc_posts = [
            {
                "id": "urn:li:share:other",
                "commentary": "Other post",
                "content": {},
                "publishedAt": 1735689600000,
                "author": "urn:li:organization:123456",
            }
        ]
        (
            patch_validate,
            patch_get_posts,
            patch_all_posts,
            patch_entity,
            patch_assets,
            patch_page,
            patch_reactions,
        ) = self._generate_update_posts_statistics_patches(ugc_posts)
        with patch_validate, patch_get_posts, patch_all_posts, patch_entity, (
            patch_assets
        ), patch_page, patch_reactions:
            self.SocialAccountLinkedin._full_resync()
        self.assertFalse(self.SocialPostAccountLinkedin.post_account_url)
        self.assertEqual(self.SocialPostAccountLinkedin.state, "deleted")
        self.assertEqual(self.SocialPostAccountLinkedin.remote_ref, remote_ref)

    def test_full_resync_reads_each_account_once(self):
        """The accounts left to the base must not come back as every account.

        The connector reconciles its own accounts and delegates the rest,
        none here, and the ordinary refresh takes an empty recordset as
        every account: without the guard of the base each account was read
        twice, once whole and once more in the ordinary way.
        """
        with self.generate_patch(
            model_patch=PATCH_SYNC_ACCOUNT_LINKEDIN.format("_import_linkedin_posts"),
            return_value=True,
        ) as mock_refresh:
            self.SocialAccountLinkedin._full_resync()
        mock_refresh.assert_called_once_with(self.SocialAccountLinkedin, full_feed=True)

    def test_update_posts_statistics_keeps_a_publication_off_the_page(self):
        """Update no longer walks the feed, so it cannot conclude a deletion.

        The publication missing from the page of recently modified ones is not
        gone: nothing was read that could say so. Only the full resync decides
        that, which is what ``test_full_resync_cleans_stale_urns`` covers.
        """
        ugc_posts = [
            {
                "id": "urn:li:share:other",
                "commentary": "Other post",
                "content": {},
                "publishedAt": 1735689600000,
                "author": "urn:li:organization:123456",
            }
        ]
        (
            patch_validate,
            patch_get_posts,
            patch_all_posts,
            patch_entity,
            patch_assets,
            patch_page,
            patch_reactions,
        ) = self._generate_update_posts_statistics_patches(ugc_posts)
        with patch_validate, patch_get_posts as mock_get_posts, (
            patch_all_posts
        ) as mock_all_posts, patch_entity, patch_assets, patch_page, patch_reactions:
            self.SocialAccountLinkedin._update_posts_statistics(False, None)
        self.assertEqual(self.SocialPostAccountLinkedin.state, "posted")
        mock_all_posts.assert_not_called()
        mock_get_posts.assert_called_once()
        self.assertEqual(
            mock_get_posts.call_args.kwargs.get("params_values", {}).get("sortBy"),
            "LAST_MODIFIED",
            msg="The page has to be the one of the recently modified posts.",
        )

    def test_update_posts_statistics_refreshes_a_publication_off_the_page(self):
        """The figures of a stored publication are refreshed without the feed.

        It is the whole point of the change: the statistics are asked for by
        URN, and Odoo already knows the URNs of the account, so a publication
        the discovery page did not bring still gets its figures.
        """
        post_account = self.SocialPostAccountLinkedin
        post_account.write({"like_count": 0, "impression_count": 0})
        ugc_posts = [
            {
                "id": "urn:li:share:other",
                "commentary": "Other post",
                "content": {},
                "publishedAt": 1735689600000,
                "author": "urn:li:organization:123456",
            }
        ]
        (
            patch_validate,
            patch_get_posts,
            patch_all_posts,
            __,
            patch_assets,
            patch_page,
            patch_reactions,
        ) = self._generate_update_posts_statistics_patches(ugc_posts)
        statistics = {post_account.remote_ref: (1, 7, 2, 0, 0.5, 42)}
        patch_entity = patch(
            PATCH_SYNC_ACCOUNT_LINKEDIN.format("_get_entity_statistics"),
            autospec=True,
            return_value=statistics,
        )
        with patch_validate, patch_get_posts, patch_all_posts, (
            patch_entity
        ) as mock_entity, patch_assets, patch_page, patch_reactions:
            self.SocialAccountLinkedin._update_posts_statistics(False, None)
        asked = [post["id"] for post in mock_entity.call_args.kwargs.get("posts") or []]
        self.assertIn(
            post_account.remote_ref,
            asked,
            msg="The stored URNs are asked about even when the page misses them.",
        )
        self.assertEqual(post_account.like_count, 7)
        self.assertEqual(post_account.impression_count, 42)
        self.assertEqual(
            post_account.state,
            "posted",
            msg="Refreshing the figures must not touch the state.",
        )

    def test_update_posts_statistics_partial_feed_keeps_the_publications(self):
        """A feed read partially says nothing about what is missing from it."""
        ugc_posts = [
            {
                "id": "urn:li:share:other",
                "commentary": "Other post",
                "content": {},
                "publishedAt": 1735689600000,
                "author": "urn:li:organization:123456",
            }
        ]
        (
            patch_validate,
            patch_get_posts,
            patch_all_posts,
            patch_entity,
            patch_assets,
            patch_page,
            patch_reactions,
        ) = self._generate_update_posts_statistics_patches(
            ugc_posts, feed_is_complete=False
        )
        with patch_validate, patch_get_posts, patch_all_posts, patch_entity, (
            patch_assets
        ), patch_page, patch_reactions:
            self.SocialAccountLinkedin._update_posts_statistics(False, None)
        self.assertEqual(self.SocialPostAccountLinkedin.state, "posted")
        self.assertEqual(self.SocialPostAccountLinkedin.remote_ref, "1234567890")

    def test_update_posts_statistics_restores_a_publication_back_online(self):
        """A line wrongly marked is recognised again by its remote reference."""
        post_account = self.SocialPostAccountLinkedin
        post_account.write({"state": "deleted", "post_account_url": False})
        ugc_posts = [
            {
                "id": post_account.remote_ref,
                "commentary": "Back online",
                "content": {},
                "publishedAt": 1735689600000,
                "author": "urn:li:organization:123456",
            }
        ]
        (
            patch_validate,
            patch_get_posts,
            patch_all_posts,
            patch_entity,
            patch_assets,
            patch_page,
            patch_reactions,
        ) = self._generate_update_posts_statistics_patches(ugc_posts)
        with patch_validate, patch_get_posts, patch_all_posts, patch_entity, (
            patch_assets
        ), patch_page, patch_reactions:
            self.SocialAccountLinkedin._update_posts_statistics(False, None)
        self.assertEqual(post_account.state, "posted")
        self.assertTrue(post_account.post_account_url)

    def test_the_initial_sync_backfills_the_account(self):
        self._isolate_linkedin_account()
        self.SocialAccountLinkedin.write({"pending_initial_sync": True})
        with self._patch_reader(
            {"2025-01-01": (0, 0, 0, 0, 0.0, 3)}
        ) as mock_reader, patch(
            PATCH_SYNC_ACCOUNT_LINKEDIN.format("_import_linkedin_posts"), autospec=True
        ):
            self.SocialAccount._run_initial_sync()
        self.assertEqual(
            len(mock_reader.call_args_list),
            len(
                self.SocialAccountLinkedin._linkedin_statistics_chunks(
                    *self.SocialAccountLinkedin._linkedin_backfill_window()
                )
            ),
            msg="The whole window is asked for in as many calls as it takes.",
        )
        self.assertEqual(len(self._statistics_of(self.SocialAccountLinkedin)), 1)
        self.assertFalse(self.SocialAccountLinkedin.pending_initial_sync)

    def test_a_failing_backfill_keeps_the_posts_already_imported(self):
        """The history costs its own calls, so it gets its own savepoint."""
        self._isolate_linkedin_account()
        self.SocialAccountLinkedin.write({"pending_initial_sync": True})
        with self._patch_reader(side_effect=UserError(_("history unavailable"))), patch(
            PATCH_SYNC_ACCOUNT_LINKEDIN.format("_import_linkedin_posts"), autospec=True
        ) as mock_refresh, mute_logger(
            "odoo.addons.social_media_linkedin.models.social_account"
        ):
            self.SocialAccount._run_initial_sync()
        mock_refresh.assert_called_once()
        self.assertFalse(self.SocialAccountLinkedin.pending_initial_sync)
        self.assertFalse(self._statistics_of(self.SocialAccountLinkedin))

    def test_the_initial_sync_does_not_ask_for_the_history_twice(self):
        """The association already filled it, so this savepoint has nothing to do."""
        self._isolate_linkedin_account()
        self.SocialAccountLinkedin.write({"pending_initial_sync": True})
        refresh_from = self.SocialAccountLinkedin._linkedin_refresh_window()[0]
        self.env["social.account.statistics"].create(
            {
                "account_id": self.SocialAccountLinkedin.id,
                "date": refresh_from - relativedelta(days=1),
                "impression_count": 10,
            }
        )
        with self._patch_reader() as mock_reader, patch(
            PATCH_SYNC_ACCOUNT_LINKEDIN.format("_import_linkedin_posts"), autospec=True
        ):
            self.SocialAccount._run_initial_sync()
        mock_reader.assert_not_called()

    def test_the_initial_sync_retries_a_backfill_that_failed(self):
        """Only the refresh window is written, so the history never got in."""
        self._isolate_linkedin_account()
        self.SocialAccountLinkedin.write({"pending_initial_sync": True})
        refresh_from = self.SocialAccountLinkedin._linkedin_refresh_window()[0]
        self.env["social.account.statistics"].create(
            {
                "account_id": self.SocialAccountLinkedin.id,
                "date": refresh_from,
                "impression_count": 10,
            }
        )
        with self._patch_reader() as mock_reader, patch(
            PATCH_SYNC_ACCOUNT_LINKEDIN.format("_import_linkedin_posts"), autospec=True
        ):
            self.SocialAccount._run_initial_sync()
        self.assertTrue(mock_reader.called)

    def test_get_entity_statistics_does_not_mutate_params(self):
        params_fields = ["q", "organizationalEntity"]
        params_values = {
            "q": "organizationalEntity",
            "organizationalEntity": "urn:li:organization:123456",
        }
        with patch(
            PATCH_SYNC_ACCOUNT_LINKEDIN.format("_get_entity_share_statistics"),
            autospec=True,
            return_value={},
        ), patch(
            PATCH_SYNC_ACCOUNT_LINKEDIN.format("_get_ugc_posts_statistics"),
            autospec=True,
            return_value={},
        ):
            self.SocialAccountLinkedin._get_entity_statistics(
                posts=[{"id": "urn:li:ugcPost:1"}],
                params_fields=params_fields,
                params_values=params_values,
            )
        self.assertEqual(params_fields, ["q", "organizationalEntity"])
        self.assertEqual(
            params_values,
            {
                "q": "organizationalEntity",
                "organizationalEntity": "urn:li:organization:123456",
            },
        )

    def test_get_entity_share_statistics_of_the_shares(self):
        params_fields = ["q"]
        params_values = {"q": "organizationalEntity"}
        self.assertEqual(
            self.SocialAccountLinkedin._get_entity_share_statistics(
                [],
                "shares",
                "share",
                "boom",
                params_fields=params_fields,
                params_values=params_values,
            ),
            {},
            msg="Nothing of this kind in the feed, nothing to ask for.",
        )
        self.assertNotIn("shares", params_fields)
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "elements": [
                {
                    "share": "urn:li:share:1",
                    "totalShareStatistics": {
                        "clickCount": 1,
                        "likeCount": 2,
                        "commentCount": 3,
                        "shareCount": 4,
                        "engagement": 0.5,
                        "impressionCount": 6,
                    },
                }
            ]
        }
        with patch(
            PATCH_ACCOUNT_LINKEDIN.format("_request_linkedin"),
            autospec=True,
            return_value=response,
        ) as mock_request:
            data = self.SocialAccountLinkedin._get_entity_share_statistics(
                ["urn:li:share:1"],
                "shares",
                "share",
                "boom",
                params_fields=params_fields,
                params_values=params_values,
            )
        self.assertEqual(data, {"urn:li:share:1": (1, 2, 3, 4, 0.5, 6)})
        self.assertEqual(
            (params_fields, params_values),
            (["q"], {"q": "organizationalEntity"}),
            msg="The parameters of the caller are left alone.",
        )
        self.assertEqual(
            mock_request.call_args.kwargs["params_values"]["shares"],
            ["urn:li:share:1"],
        )
        self.assertEqual(
            mock_request.call_args.kwargs["endpoint"],
            "/organizationalEntityShareStatistics",
        )
        error_response = MagicMock(status_code=400)
        error_response.json.return_value = {"message": "Invalid share urn"}
        with patch(
            PATCH_ACCOUNT_LINKEDIN.format("_request_linkedin"),
            autospec=True,
            return_value=error_response,
        ):
            with self.assertRaises(UserError):
                self.SocialAccountLinkedin._get_entity_share_statistics(
                    ["urn:li:share:1"],
                    "shares",
                    "share",
                    "boom",
                    params_fields=["q"],
                    params_values={"q": "organizationalEntity"},
                )

    def test_get_ugc_posts_statistics(self):
        self.assertEqual(self.SocialAccountLinkedin._get_ugc_posts_statistics(), {})
        params_fields = ["q"]
        params_values = {"q": "organizationalEntity"}
        self.assertEqual(
            self.SocialAccountLinkedin._get_ugc_posts_statistics(
                posts=[{"id": "urn:li:share:1"}],
                params_fields=params_fields,
                params_values=params_values,
            ),
            {},
            msg="The UGC posts endpoint ignores the shares.",
        )
        self.assertNotIn("ids", params_fields)
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "results": {
                "urn:li:ugcPost:1": {
                    "likesSummary": {"totalLikes": 7},
                    "commentsSummary": {"aggregatedTotalComments": 8},
                }
            }
        }
        with patch(
            PATCH_ACCOUNT_LINKEDIN.format("_request_linkedin"),
            autospec=True,
            return_value=response,
        ) as mock_request:
            data = self.SocialAccountLinkedin._get_ugc_posts_statistics(
                posts=[{"id": "urn:li:ugcPost:1"}, {"id": "urn:li:share:2"}],
                params_fields=params_fields,
                params_values=params_values,
            )
        self.assertEqual(
            data,
            {"urn:li:ugcPost:1": (7, 8)},
            msg="socialActions only knows the likes and the comments.",
        )
        self.assertEqual(
            (params_fields, params_values),
            (["q"], {"q": "organizationalEntity"}),
            msg="The parameters of the caller are left alone.",
        )
        self.assertEqual(
            mock_request.call_args.kwargs["params_values"]["ids"],
            ["urn:li:ugcPost:1"],
        )
        self.assertEqual(mock_request.call_args.kwargs["endpoint"], "/socialActions")
        error_response = MagicMock(status_code=400)
        error_response.json.return_value = {"message": "Invalid ugc post urn"}
        with patch(
            PATCH_ACCOUNT_LINKEDIN.format("_request_linkedin"),
            autospec=True,
            return_value=error_response,
        ):
            with self.assertRaises(UserError):
                self.SocialAccountLinkedin._get_ugc_posts_statistics(
                    posts=[{"id": "urn:li:ugcPost:1"}],
                    params_fields=["q"],
                    params_values={"q": "organizationalEntity"},
                )

    def test_get_entity_share_statistics_splits_the_urns(self):
        """A feed of more than a page fits in no single query string."""
        urns = self._fake_urns("urn:li:share:", 250)
        response = MagicMock(status_code=200)
        response.json.return_value = {"elements": []}
        with patch(
            PATCH_ACCOUNT_LINKEDIN.format("_request_linkedin"),
            autospec=True,
            return_value=response,
        ) as mock_request:
            self.SocialAccountLinkedin._get_entity_share_statistics(
                urns,
                "shares",
                "share",
                "boom",
                params_fields=["q", "organizationalEntity"],
                params_values={
                    "q": "organizationalEntity",
                    "organizationalEntity": "urn:li:organization:123456",
                },
            )
        self.assertGreater(mock_request.call_count, 1)
        asked = []
        for call in mock_request.call_args_list:
            self.assertLess(
                len(self._linkedin_query_string(call).encode()),
                _QUERY_STRING_MAX_BYTES_LINKEDIN,
            )
            asked.extend(call.kwargs["params_values"]["shares"][0].split(","))
        self.assertEqual(asked, urns, msg="Every URN is asked for exactly once.")

    def test_get_ugc_posts_statistics_splits_the_urns(self):
        urns = self._fake_urns("urn:li:ugcPost:", 250)
        response = MagicMock(status_code=200)
        response.json.return_value = {"results": {}}
        with patch(
            PATCH_ACCOUNT_LINKEDIN.format("_request_linkedin"),
            autospec=True,
            return_value=response,
        ) as mock_request:
            self.SocialAccountLinkedin._get_ugc_posts_statistics(
                posts=[{"id": urn} for urn in urns],
                params_fields=[],
                params_values={},
            )
        self.assertGreater(mock_request.call_count, 1)
        asked = []
        for call in mock_request.call_args_list:
            self.assertLess(
                len(self._linkedin_query_string(call).encode()),
                _QUERY_STRING_MAX_BYTES_LINKEDIN,
            )
            asked.extend(call.kwargs["params_values"]["ids"][0].split(","))
        self.assertEqual(asked, urns)

    def test_get_entity_share_statistics_of_the_ugc_posts(self):
        """The UGC posts answer the same block of figures as the shares."""
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "elements": [
                {
                    "ugcPost": "urn:li:ugcPost:1",
                    "totalShareStatistics": {
                        "clickCount": 9,
                        "likeCount": 1,
                        "commentCount": 2,
                        "shareCount": 3,
                        "engagement": 0.25,
                        "impressionCount": 40,
                    },
                },
                {"organizationalEntity": "urn:li:organization:123456"},
            ]
        }
        with patch(
            PATCH_ACCOUNT_LINKEDIN.format("_request_linkedin"),
            autospec=True,
            return_value=response,
        ) as mock_request:
            data = self.SocialAccountLinkedin._get_entity_share_statistics(
                ["urn:li:ugcPost:1"],
                "ugcPosts",
                "ugcPost",
                "boom",
                params_fields=["q"],
                params_values={"q": "organizationalEntity"},
            )
        self.assertEqual(
            data,
            {"urn:li:ugcPost:1": (9, 1, 2, 3, 0.25, 40)},
            msg="The aggregate element, which names no entity, is left out.",
        )
        self.assertEqual(
            mock_request.call_args.kwargs["params_values"]["ugcPosts"],
            ["urn:li:ugcPost:1"],
        )
        self.assertEqual(
            mock_request.call_args.kwargs["endpoint"],
            "/organizationalEntityShareStatistics",
        )
        error_response = MagicMock(status_code=400)
        error_response.json.return_value = {"message": "Invalid ugc post urn"}
        with patch(
            PATCH_ACCOUNT_LINKEDIN.format("_request_linkedin"),
            autospec=True,
            return_value=error_response,
        ):
            with self.assertRaises(UserError):
                self.SocialAccountLinkedin._get_entity_share_statistics(
                    ["urn:li:ugcPost:1"],
                    "ugcPosts",
                    "ugcPost",
                    "boom",
                    params_fields=["q"],
                    params_values={"q": "organizationalEntity"},
                )

    def test_get_entity_statistics_merges_the_two_ugc_sources(self):
        """A UGC post keeps its figures and takes its likes from the feed."""
        entity_answers = {
            "shares": {"urn:li:share:1": (1, 2, 3, 4, 0.5, 6)},
            "ugcPosts": {"urn:li:ugcPost:1": (9, 0, 0, 3, 0.25, 40)},
        }
        with patch(
            PATCH_SYNC_ACCOUNT_LINKEDIN.format("_get_entity_share_statistics"),
            autospec=True,
            side_effect=lambda account, urns, param_field, *args, **kwargs: (
                entity_answers[param_field]
            ),
        ), patch(
            PATCH_SYNC_ACCOUNT_LINKEDIN.format("_get_ugc_posts_statistics"),
            autospec=True,
            return_value={"urn:li:ugcPost:1": (7, 8), "urn:li:ugcPost:2": (1, 2)},
        ) as mock_social_actions:
            data = self.SocialAccountLinkedin._get_entity_statistics(
                posts=[{"id": "urn:li:share:1"}, {"id": "urn:li:ugcPost:1"}]
            )
        self.assertEqual(
            data,
            {
                "urn:li:share:1": (1, 2, 3, 4, 0.5, 6),
                "urn:li:ugcPost:1": (9, 7, 8, 3, 0.25, 40),
                "urn:li:ugcPost:2": (0, 1, 2, 0, 0, 0),
            },
        )
        self.assertEqual(
            mock_social_actions.call_args.kwargs["params_fields"],
            [],
            msg="socialActions takes neither the finder nor the organization.",
        )
        self.assertEqual(mock_social_actions.call_args.kwargs["params_values"], {})

    @mute_logger(LOGGER_ACCOUNT_LINKEDIN, LOGGER_ACCOUNT_SYNC_LINKEDIN)
    def test_update_posts_statistics_isolates_each_account(self):
        """A failing account is rolled back alone, the other one is refreshed."""
        failing = self.SocialAccountLinkedin
        working = self.SocialAccountLinkedinData
        stale = self.SocialPostAccountLinkedin
        ugc_posts = [
            {
                "id": "urn:li:share:other",
                "commentary": "Other post",
                "content": {},
                "publishedAt": 1735689600000,
                "author": "urn:li:organization:123456",
            }
        ]
        (
            patch_validate,
            patch_get_posts,
            patch_all_posts,
            __,
            patch_assets,
            patch_page,
            patch_reactions,
        ) = self._generate_update_posts_statistics_patches(ugc_posts)

        def entity_statistics(account, *args, **kwargs):
            if account.id == failing.id:
                raise UserError(_("LinkedIn refused the statistics"))
            return {}

        patch_entity = self.generate_patch(
            **{
                "model_patch": PATCH_SYNC_ACCOUNT_LINKEDIN.format(
                    "_get_entity_statistics"
                ),
                "side_effect": entity_statistics,
            }
        )
        with patch_validate, patch_get_posts, patch_all_posts, patch_entity, (
            patch_assets
        ), patch_page, patch_reactions:
            (failing | working)._update_posts_statistics(False, None)
        self.env.invalidate_all()
        self.assertEqual(
            stale.state,
            "posted",
            msg="The sweep of the failing account was rolled back with it.",
        )
        self.assertTrue(
            working.post_account_ids.filtered(
                lambda line: line.remote_ref == "urn:li:share:other"
            ),
            msg="The account that did not fail was refreshed all the same.",
        )

    def _generate_update_posts_statistics_patches(
        self, ugc_posts, feed_is_complete=True
    ):
        """Patches of a statistics pass.

        ``feed_is_complete`` is what the feed reader answers along the posts:
        the sweep of the publications gone from LinkedIn only runs when the
        whole feed was read.
        """
        return (
            self.generate_patch(
                **{
                    "model_patch": PATCH_ACCOUNT_LINKEDIN.format(
                        "validate_access_token"
                    ),
                    "return_value": True,
                }
            ),
            self.generate_patch(
                **{
                    "model_patch": PATCH_ACCOUNT_LINKEDIN.format("_get_posts"),
                    "return_value": ugc_posts,
                }
            ),
            self.generate_patch(
                **{
                    "model_patch": PATCH_SYNC_ACCOUNT_LINKEDIN.format("_get_all_posts"),
                    "return_value": (ugc_posts, feed_is_complete),
                }
            ),
            self.generate_patch(
                **{
                    "model_patch": PATCH_SYNC_ACCOUNT_LINKEDIN.format(
                        "_get_entity_statistics"
                    ),
                    "side_effect": lambda *args, **kwargs: {},
                }
            ),
            self.generate_patch(
                **{
                    "model_patch": PATCH_SYNC_POST_ACCOUNT_LINKEDIN.format(
                        "_get_assets_save"
                    ),
                    "side_effect": lambda self, *args, **kwargs: (
                        self.env["ir.attachment"],
                        {},
                    ),
                }
            ),
            self.generate_patch(
                **{
                    "model_patch": PATCH_SYNC_ACCOUNT_LINKEDIN.format(
                        "_linkedin_read_watched_figures"
                    ),
                    "return_value": dict(RECENT_STATISTICS_LINKEDIN),
                }
            ),
            self.generate_patch(
                **{
                    "model_patch": PATCH_SYNC_ACCOUNT_LINKEDIN.format("_get_reactions"),
                    # An empty set through ``return_value`` is falsy and
                    # ``generate_patch`` would build no patch at all.
                    "side_effect": lambda *args, **kwargs: set(),
                }
            ),
        )

    def _linkedin_query_string(self, call):
        """Rebuild the query string that a ``_request_linkedin`` call sends."""
        kwargs = call.kwargs
        return "&".join(
            social_url_encode(param_field, kwargs["params_values"])
            for param_field in kwargs["params_fields"]
        )

    @patch(PATCH_ACCOUNT_LINKEDIN.format("_request_linkedin"))
    def test_get_reactions(self, mock_request):
        """One batch answers the page, and ``root`` is what names the entity."""
        account = self.SocialAccountLinkedin
        reacted_urn = "urn:li:ugcPost:1"
        answered = MagicMock()
        answered.status_code = 200
        answered.json.return_value = {
            "results": {
                "asked-key": {
                    "id": f"urn:li:reaction:({account.remote_ref},{reacted_urn})",
                    "reactionType": "LIKE",
                    "root": reacted_urn,
                }
            },
            "errors": {},
        }
        mock_request.return_value = answered
        self.assertEqual(
            account._get_reactions([reacted_urn, "urn:li:ugcPost:2"]),
            {reacted_urn},
            msg="Only what LinkedIn answered is a reaction of the account.",
        )
        self.assertEqual(
            mock_request.call_count, 1, msg="The whole page costs one call."
        )
        asked = mock_request.call_args.kwargs["params_values"]["ids"][0]
        self.assertIn(linkedin_reaction_id(account.remote_ref, reacted_urn), asked)
        self.assertIn(
            quote("urn:li:ugcPost:2", safe=""),
            asked,
            msg="The entities without a reaction are asked about all the same.",
        )

    @patch(PATCH_ACCOUNT_LINKEDIN.format("_request_linkedin"))
    def test_get_reactions_unreadable(self, mock_request):
        """Not knowing is not the same as not having reacted."""
        failed = MagicMock()
        failed.status_code = 403
        mock_request.return_value = failed
        self.assertIsNone(
            self.SocialAccountLinkedin._get_reactions(["urn:li:ugcPost:1"])
        )
        self.assertEqual(
            self.SocialAccountLinkedin._linkedin_reaction_values(
                "urn:li:ugcPost:1", None
            ),
            {},
            msg="Nothing is written when LinkedIn did not answer.",
        )
