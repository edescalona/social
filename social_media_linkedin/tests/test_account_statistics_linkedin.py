# Copyright 2026 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import MagicMock, patch

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from ..social_linkedin_utils import _QUERY_STRING_MAX_BYTES_LINKEDIN
from .test_common_linkedin import PATCH_ACCOUNT_LINKEDIN, TestSocialCommonLinkedin


@tagged("post_install", "-at_install")
class TestLinkedinPostStatistics(TestSocialCommonLinkedin):
    """The figures LinkedIn reports for a publication, read by URN.

    Three calls answer a whole page of publications, which is what lets the
    connector read them without importing anything: Odoo already knows the
    URNs of what it published.
    """

    def test_get_entity_statistics_does_not_mutate_params(self):
        params_fields = ["q", "organizationalEntity"]
        params_values = {
            "q": "organizationalEntity",
            "organizationalEntity": "urn:li:organization:123456",
        }
        with patch(
            PATCH_ACCOUNT_LINKEDIN.format("_get_entity_share_statistics"),
            autospec=True,
            return_value={},
        ), patch(
            PATCH_ACCOUNT_LINKEDIN.format("_get_ugc_posts_statistics"),
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
            PATCH_ACCOUNT_LINKEDIN.format("_get_entity_share_statistics"),
            autospec=True,
            side_effect=lambda account, urns, param_field, *args, **kwargs: (
                entity_answers[param_field]
            ),
        ), patch(
            PATCH_ACCOUNT_LINKEDIN.format("_get_ugc_posts_statistics"),
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
