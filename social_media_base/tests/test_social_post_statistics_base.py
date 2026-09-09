# Copyright 2026 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.addons.social_media_base.models.social_account import (
    STATISTICS_WINDOW_DAYS,
)

from .test_social_common import TestSocialMediaBaseCommon


class TestSocialPostStatisticsBase(TestSocialMediaBaseCommon):
    """Reading the figures of a publication back from the social media."""

    def test_statistics_date_starts_empty(self):
        """A publication nobody read carries no date.

        It is what tells a zero nobody asked about apart from a zero the
        social media really reported.
        """
        self.assertFalse(self.social_post_account_id.statistics_date)

    def test_statistics_date_is_readonly(self):
        """Only the refresh writes the date, never the user."""
        field = self.SocialPostAccount._fields["statistics_date"]
        self.assertTrue(field.readonly)
        self.assertFalse(field.copy)

    def test_statistics_window_is_a_month(self):
        """The window is a constant of the module, not a setting.

        It is the cost decision that lets this pass live in
        ``social_media_base``, so it is not a preference to widen.
        """
        self.assertEqual(STATISTICS_WINDOW_DAYS, 30)
