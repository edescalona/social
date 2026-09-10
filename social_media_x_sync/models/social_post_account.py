# Copyright 2026 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from collections import Counter

from tweepy.errors import TooManyRequests

from odoo import _, fields, models

from ..social_x_sync_utils import _SEARCH_MAX_RESULTS_X

_logger = logging.getLogger(__name__)


class SocialPostAccount(models.Model):
    """Publication, comments and statistics of a post on an X account."""

    _inherit = "social.post.account"

    def _x_comment_parent_ref(self, tweet, comment_refs):
        """Return the comment a tweet of the thread answers.

        The search that reads the comments asks for the whole conversation, so
        the replies of a reply arrive in the same answer as the comments of
        the post. What tells them apart is already in the payload: the
        ``replied_to`` reference of a comment is the post, and that of a reply
        is another tweet of the list.

        :param tweet: one tweet as X answered it.
        :param comment_refs: the references of every tweet of the thread.
        :return: the reference of the answered comment, ``False`` when the
            tweet hangs from the publication.
        :rtype: str or bool
        """
        for referenced in getattr(tweet, "referenced_tweets", None) or []:
            if referenced.type != "replied_to":
                continue
            parent_ref = str(referenced.id)
            return parent_ref if parent_ref in comment_refs else False
        return False

    def _x_comments_quota_answer(self):
        """Answer of a read the quota of X did not let happen.

        The details —limit, remaining and when to retry— are already on their
        way to the user from :meth:`_get_message_many_requests`, so what
        travels here is only what the client needs to tell an unread thread
        from a publication with no comments.

        :rtype: dict
        """
        return {
            "success": False,
            "message": _(
                "The comments could not be read from X. The account may have "
                "reached the limit of requests of its plan."
            ),
        }

    def _x_comment_quota_answer(self):
        """Answer of a reply the quota of X did not let happen.

        The details —limit, remaining and when to retry— are already on their
        way to the user from :meth:`_get_message_many_requests`, so what
        travels here is only what the client needs to tell a reply X never
        received from one it published.

        :rtype: dict
        """
        return {
            "success": False,
            "message": _(
                "The comment could not be published on X. The account may "
                "have reached the limit of requests of its plan."
            ),
            "post_deleted": False,
        }

    def get_comments(self):
        """Read the replies to this post.

        :return: ``success`` and the list of comments, or the error message.
        :rtype: dict
        """
        data = super().get_comments()
        comments = []
        if "x" == self.account_id.media_type:
            try:
                result = self.account_id._valid_time_request(endpoint="get_comments")
                if not result:
                    return self._x_comments_quota_answer()
                client_api = self.account_id.get_client_api(
                    bearer_token=self.account_id.sudo().x_access_token_oauth2
                )
                query = (
                    f"conversation_id:{self.remote_ref} "
                    f"is:reply -is:retweet -is:quote"
                )
                response = client_api.search_recent_tweets(
                    query=query,
                    tweet_fields=[
                        "id",
                        "text",
                        "author_id",
                        "created_at",
                        "conversation_id",
                        "attachments",
                        "in_reply_to_user_id",
                    ],
                    expansions=[
                        "author_id",
                        "in_reply_to_user_id",
                        "referenced_tweets.id",
                        "attachments.media_keys",
                        "referenced_tweets.id.author_id",
                    ],
                    user_fields="id,name,username,profile_image_url",
                    media_fields=["media_key", "type", "url"],
                    max_results=_SEARCH_MAX_RESULTS_X,
                )
                if response.data:
                    comments = []
                    comment_refs = {str(tweet.id) for tweet in response.data}
                    users = {
                        str(u.id): u for u in (response.includes.get("users", []) or [])
                    }
                    media_urls = {
                        media.media_key: media.url
                        for media in (response.includes.get("media") or [])
                        if media.url
                    }
                    for comment in response.data or []:
                        author = users.get(str(comment.author_id))
                        media_keys = (getattr(comment, "attachments", {}) or {}).get(
                            "media_keys", []
                        )
                        comments.append(
                            {
                                "id": str(comment.id),
                                # On X a comment is a tweet, so what names
                                # it is its own identifier, and that is
                                # what a reply is published against.
                                "remote_ref": str(comment.id),
                                "parent_ref": self._x_comment_parent_ref(
                                    comment, comment_refs
                                ),
                                "text": comment.text,
                                "actor": author.name,
                                # X stamps a tweet with a moment carrying its
                                # offset, and what the client draws is how
                                # long ago it was, the same sentence every
                                # social media answers with.
                                "published_time": self._format_published_time(
                                    comment.created_at
                                ),
                                "author_image": author.profile_image_url
                                if author.profile_image_url
                                else None,
                                "images_url": [
                                    media_urls[media_key]
                                    for media_key in media_keys
                                    if media_key in media_urls
                                ],
                            }
                        )
                    # The whole thread already arrived, so how many
                    # replies each comment has is counted here and never
                    # asked to X again.
                    reply_counts = Counter(
                        comment["parent_ref"]
                        for comment in comments
                        if comment["parent_ref"]
                    )
                    for comment in comments:
                        comment["reply_count"] = reply_counts.get(
                            comment["remote_ref"], 0
                        )

            except TooManyRequests as exManyRequest:
                self.account_id._get_message_many_requests(
                    exManyRequest, endpoint="get_comments"
                )
                return self._x_comments_quota_answer()
            except Exception as e:  # noqa: BLE001 - tweepy may fail in any way
                return_message = _("Error Get Comments for Tweet: %(error)s", error=e)
                _logger.exception(
                    "Error getting the comments of tweet %s", self.remote_ref
                )
                return {
                    "success": False,
                    "message": return_message,
                }
            return {
                "success": True,
                "data": data.get("data", []) + comments,
            }
        # Answered untouched, ``success`` included: what another social media
        # said about its own comments is not this connector's to rewrite, and
        # the message explaining a failure of its own would go with it.
        return data

    def create_x_comment(self, post_data):
        """Publish a reply to this post, with its attachments if any.

        :rtype: dict
        """
        if "x" == self.account_id.media_type:
            try:
                result = self.account_id._valid_time_request(endpoint="create_comment")
                if not result:
                    return self._x_comment_quota_answer()
                client_api = self.account_id.get_client_api()
                # A reply to a comment answers that tweet instead of the
                # post: on X both are tweets and the only difference is
                # which one is being replied to.
                parent_ref = post_data.get("social_parent_ref")
                target = parent_ref or self.remote_ref
                attachment_ids = self.env["ir.attachment"]
                if post_data.get("attachment_ids", False) and post_data.get(
                    "body", False
                ):
                    attachment_ids = self.env["ir.attachment"].browse(
                        post_data.get("attachment_ids", [])
                    )
                    # The images of a comment are not stored on the
                    # publication, so only what X calls them is needed.
                    media_refs = self.account_id._prepare_medias_for_tweet(
                        image_ids=attachment_ids
                    )
                    response = client_api.create_tweet(
                        text=post_data.get("body", ""),
                        in_reply_to_tweet_id=target,
                        media_ids=list(media_refs.values()),
                    )
                else:
                    response = client_api.create_tweet(
                        text=post_data.get("body", ""),
                        in_reply_to_tweet_id=target,
                    )
            except TooManyRequests as exManyRequest:
                self.account_id._get_message_many_requests(
                    exManyRequest, endpoint="create_comment"
                )
                return self._x_comment_quota_answer()
            except Exception as exp:  # noqa: BLE001 - tweepy may fail in any way
                # X refuses a reply to a post that is gone in more than one
                # shape — a ``400`` and a ``403`` both mean it — so the post
                # itself is asked about instead of reading the error.
                post_deleted = self._remote_post_gone_on_action()
                return_message = (
                    _("The post does not exist or has been deleted.")
                    if post_deleted
                    else _("Error Comment Tweet: %(error)s", error=exp)
                )
                _logger.exception("Error replying to tweet %s", self.remote_ref)
                return {
                    "success": False,
                    "message": return_message,
                    "post_deleted": post_deleted,
                }
            return {
                "success": True,
                "post_deleted": False,
                **self._x_created_comment(response, parent_ref, attachment_ids),
            }
        return {
            "success": True,
            "post_deleted": False,
        }

    def _x_created_comment(self, response, parent_ref, attachments):
        """Shape the tweet X answers as the comment the client draws.

        X answers the creation with the identifier and the text of the tweet,
        and everything else is known here without asking: the comment was
        written by this account, at this moment, with the images that went up
        with it. A creation that answers no identifier answers nothing, and
        the client rereads the thread instead.

        :param response: the answer of tweepy to the creation.
        :param parent_ref: the comment the tweet answers, ``False`` when it
            hangs from the publication.
        :param attachments: the images published with the comment.
        :return: ``{"comment": …}``, or empty when it cannot be shaped.
        :rtype: dict
        """
        data = getattr(response, "data", None) or {}
        remote_ref = str(data.get("id") or "")
        if not remote_ref:
            return {}
        return {
            "comment": {
                "id": remote_ref,
                "remote_ref": remote_ref,
                "parent_ref": parent_ref or False,
                # What X stored, which is not always what was sent: the text
                # comes back shortened when it carries a link.
                "text": data.get("text") or "",
                "actor": self.account_id.name,
                # The reply was written just now, and the client draws how
                # long ago that is like it does for every other comment.
                "published_time": self._format_published_time(fields.Datetime.now()),
                "author_image": None,
                "images_url": [
                    f"/web/image/{attachment.id}" for attachment in attachments
                ],
                "reply_count": 0,
                "liked": False,
            }
        }

    def create_comment(self, post_data, context=None):
        if "x" == self.account_id.media_type:
            return self.create_x_comment(post_data)
        else:
            return super().create_comment(post_data, context)

    def _get_assets_save_x(self, media_keys, media_map):
        """Download the media of a tweet that are not stored yet.

        :return: The attachments created and the media key of each one, keyed
            by its identifier. Both go into the same write, so that a
            downloaded media is never stored without the reference telling it
            apart from one attached in Odoo.
        :rtype: tuple
        """
        medias_exist = self._get_medias_account(media_keys)
        url_by_ref = {}
        for media in media_keys:
            if media in medias_exist:
                continue
            media_data = media_map.get(media)
            url_by_ref[media] = media_data and media_data[1]
        return self._store_remote_medias(url_by_ref)
