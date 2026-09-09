# Copyright 2026 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from tweepy.errors import TooManyRequests

from odoo import _, models
from odoo.exceptions import UserError

from ..social_x_utils import _URL_X

_logger = logging.getLogger(__name__)


class SocialPostAccount(models.Model):
    """Publishing and deletion of a post on an X account."""

    _inherit = "social.post.account"

    def _action_post(self, post_id):
        res = super()._action_post(post_id)
        if any(account.media_type == "x" for account in post_id.account_ids):
            post_accounts = post_id._filter_by_media_types(["x"])
            images, videos = post_id._medias_for_publication()
            for post_account in post_accounts:
                with post_account._publish_guard():
                    post_account._check_publishable()
                    (
                        post_account_id,
                        media_refs,
                    ) = post_account._publish_attempt(
                        post_account.account_id.create_tweet,
                        message=post_account.message,
                        image_ids=images,
                        video_ids=videos,
                        post_id=post_id,
                        post_account_id=post_account,
                    )
                    if post_account_id:
                        post_account._register_publish_success(
                            post_account_id,
                            f"{_URL_X}{post_account.account_id.username}"
                            f"/status/{post_account_id}",
                            media_refs,
                            bool(videos),
                        )
                    else:
                        post_account._register_publish_refused(
                            _(
                                "X did not accept the post. The account may "
                                "have reached the limit of requests of its "
                                "plan: check the account and try again later."
                            )
                        )
        return res

    def _delete_post_account(self):
        """Delete the tweet of this publication before its line goes.

        The caller unlinks the line right after this, and the line is the only
        place holding ``remote_ref``, so a deletion X did not confirm has to
        stop here: otherwise the tweet stays published with nothing in Odoo
        pointing at it. The quota is such a deletion, and it is raised with
        the same reason the publication gives, because it is a time to wait
        and not a post X refused.
        """
        if self.media_id.media_type == "x":
            message_error = ""
            quota_error = _(
                "The post could not be deleted on X. The account may have "
                "reached the limit of requests of its plan: check the account "
                "and try again later."
            )
            try:
                if self.remote_ref:
                    # Asking about the quota is not a mute question: with the
                    # window still open it tells the user when to retry. On a
                    # line that never reached X there is nothing to delete, so
                    # there is nothing to warn about either.
                    if not self.account_id._valid_time_request(endpoint="delete_post"):
                        message_error = quota_error
                    else:
                        client_api = self.account_id.get_client_api(
                            bearer_token=self.account_id.sudo().x_access_token_oauth2
                        )
                        response = client_api.delete_tweet(self.remote_ref)
                        if response.errors:
                            # tweepy answers the errors as dicts, so what X
                            # said is under its message key; the dict itself
                            # is the fallback for a shape without one.
                            message_error = ", ".join(
                                str(
                                    error.get("detail") or error.get("message") or error
                                )
                                for error in response.errors
                            )
            except TooManyRequests as exManyRequest:
                self.account_id._get_message_many_requests(
                    exManyRequest, endpoint="delete_post"
                )
                message_error = quota_error
            except Exception as e:  # noqa: BLE001 - tweepy may fail in any way
                message_error = _("ERROR DELETE POST X: %(error)s", error=e)
                _logger.exception("Error deleting tweet %s", self.remote_ref)
            if message_error:
                raise UserError(message_error)
        return super()._delete_post_account()
