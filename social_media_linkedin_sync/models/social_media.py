# Copyright 2026 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models

from ..social_linkedin_sync_utils import _SCOPE_SYNC_LINKEDIN


class SocialMedia(models.Model):
    _inherit = "social.media"

    def _get_linkedin_scopes(self):
        """Append the scopes the import of the history needs.

        A token keeps the scopes it was issued with, so an account authorized
        before this module was installed has to be associated again before the
        import can read its publications.
        """
        scopes = super()._get_linkedin_scopes()
        return scopes + [s for s in _SCOPE_SYNC_LINKEDIN if s not in scopes]
