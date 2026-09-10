# Copyright 2026 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    social_media_sync_media_max_age_days = fields.Integer(
        "Max age in days of the medias downloaded from the social media",
        config_parameter="social_media_sync.media_max_age_days",
        help="If set as a positive integer, the images and videos downloaded "
        "from the social media are released from the publications older than "
        "that, and the files are removed by the vacuum. What each social "
        "media made of them is kept, so the publications are not downloaded "
        "again.",
    )
