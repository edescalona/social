# Copyright 2026 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).


from unittest.mock import patch

from odoo.addons.social_media_linkedin.social_linkedin_utils import (
    _SCOPE_LINKEDIN,
    _SCOPE_OPTIONAL_LINKEDIN,
)

from ..social_linkedin_sync_utils import (
    _SCOPE_OPTIONAL_SYNC_LINKEDIN,
    _SCOPE_SYNC_LINKEDIN,
)
from .test_sync_linkedin_common import TestSocialSyncCommonLinkedin


class TestSocialSyncMediaLinkedin(TestSocialSyncCommonLinkedin):
    def test_get_linkedin_scopes_adds_the_import_one(self):
        """The import contributes the permission its own calls consume."""
        scopes = self.media_linkedin_id._get_linkedin_scopes()
        self.assertEqual(scopes[: len(_SCOPE_LINKEDIN)], _SCOPE_LINKEDIN)
        for scope in _SCOPE_SYNC_LINKEDIN:
            self.assertIn(scope, scopes)
        self.assertEqual(len(scopes), len(set(scopes)))

    def test_get_linkedin_scopes_leaves_the_optional_ones_out(self):
        """Neither module asks for the scopes no call of it consumes."""
        scopes = self.media_linkedin_id._get_linkedin_scopes()
        for scope in _SCOPE_OPTIONAL_LINKEDIN + _SCOPE_OPTIONAL_SYNC_LINKEDIN:
            self.assertNotIn(scope, scopes)

    def test_action_add_account_asks_for_the_import_scope(self):
        """The consent URL carries the permission the import needs."""
        with patch.object(
            type(self.wizard_account_id),
            "_get_url_redirect",
            return_value=self.url_callback,
        ):
            url = self.wizard_account_id.with_context(
                only_url=True
            )._action_add_account()
        for scope in _SCOPE_SYNC_LINKEDIN:
            self.assertIn(scope, url)
