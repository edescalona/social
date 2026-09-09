# Copyright 2026 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import logging
from datetime import datetime

import pytz
import requests

from odoo import _, api, fields, models
from odoo.tools.misc import _format_time_ago

_logger = logging.getLogger(__name__)


class SocialPostAccount(models.Model):
    """What the publication reads back from its social media.

    Asking whether a publication is still there costs one call per
    publication, and reading a thread costs one per thread: both grow with
    what the account has published, which is why neither is in
    ``social_media_base``.
    """

    _inherit = "social.post.account"

    liked_by_account = fields.Boolean(
        string="Recommended",
        readonly=True,
        copy=False,
        help="Whether the account has a reaction of its own on this "
        "publication. It is what the Recommend entry of the dashboard "
        "toggles, and every import refreshes it from the social media.",
    )
    actor_urn = fields.Char(
        string="Author Reference",
        copy=False,
        help="Reference of the author of the publication on the social media, "
        "as the import read it. It is what the social media answers about "
        "whoever published, which is not always the account that imported it: "
        "a page publishes as the page and a person as the person.",
    )

    def action_open_post_account_url(self):
        """Ask the social media before opening the address.

        The address alone is not proof that the publication is still online:
        it survives a deletion made on the social media until a pass notices.
        Base opens it without asking because asking costs a call per
        publication; here the call is what this module is for.
        """
        result = super().action_open_post_account_url()
        if not result:
            return result
        if not self.check_post_exists():
            return self._notify_remote_post_gone()
        return result

    def check_post_exists(self):
        """Ask the social media whether this publication is still online.

        Public entry point shared by the form button and by the dashboard, so
        both answer the same thing from the same code.

        :rtype: bool
        """
        self.ensure_one()
        return self._check_remote_post_exists()

    def _check_remote_post_exists(self):
        """Whether the publication still exists, implemented by each connector.

        The contract is to fail open: ``False`` is only answered when the
        social media positively reported the publication as gone. A lost
        permission, a rate limit or a connection error must answer ``True`` and
        leave the record untouched, because a publication is not deleted just
        because Odoo could not read it.

        :rtype: bool
        """
        return bool(self.remote_ref)

    def _register_remote_post_gone(self):
        """Record that the publication no longer exists on the social media.

        ``remote_ref`` is kept on purpose: it is the only handle left on the
        publication, and detection is not infallible, so a line wrongly marked
        can be recognised and restored by the next full refresh.
        """
        self.write({"state": "deleted", "post_account_url": False})

    def _remote_post_gone_on_action(self):
        """Whether an action failed because the publication no longer exists.

        A ``404`` on a reaction or on a comment is not proof on its own: the
        social media answers the same for a reference it does not recognise or
        for a lost permission, and marking a live publication as deleted is
        worse than one extra request. The publication itself is asked about
        instead, which is also what registers the deletion once it is
        confirmed.

        The check runs from paths that are already handling a failure, so it
        answers ``False`` instead of raising: an action that could not be
        completed must report its own error, not the one of the check made
        to explain it.

        :rtype: bool
        """
        self.ensure_one()
        try:
            return not self._check_remote_post_exists()
        except Exception:  # noqa: BLE001 - a failed check is not a deletion
            _logger.exception(
                "Error checking whether the post %s still exists, it is left "
                "untouched",
                self.remote_ref,
            )
            return False

    def _notify_remote_post_gone(self):
        """Tell the user the publication is gone and refresh what is shown."""
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Post deleted [%(account)s]", account=self.account_id.name),
                "type": "warning",
                "message": _("The post does not exist or has been deleted."),
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }

    def action_like_post(self, author_urn=None):
        """Recommend the publication on the social media.

        :param author_urn: actor urn performing the reaction.
        :return: ``success`` and ``message`` of the action, plus
            ``post_deleted`` when the attempt is what revealed the publication
            is gone, so the client refreshes what it draws, and ``liked``,
            what the social media holds once the call is over --``None`` when
            it did not say, and then the client leaves the entry as it drew
            it.
        :rtype: dict
        """
        return {"success": True, "message": "", "post_deleted": False, "liked": True}

    def action_unlike_post(self, author_urn=None):
        """Withdraw the reaction of the account from the publication.

        The counterpart of :meth:`action_like_post`, and the reason the entry
        of the dashboard is a toggle instead of a one-way action.

        :param author_urn: actor urn whose reaction is withdrawn.
        :return: the same keys :meth:`action_like_post` answers.
        :rtype: dict
        """
        return {"success": True, "message": "", "post_deleted": False, "liked": False}

    def action_like_comment(self, comment_ref=None, author_urn=None):
        """Recommend a comment of the publication on the social media.

        :param comment_ref: reference of the comment on the social media, as
            ``get_comments`` answered it in ``remote_ref``.
        :param author_urn: actor urn performing the reaction.
        :return: the same keys :meth:`action_like_post` answers.
        :rtype: dict
        """
        return {"success": True, "message": "", "post_deleted": False, "liked": True}

    def action_unlike_comment(self, comment_ref=None, author_urn=None):
        """Withdraw the reaction of the account from a comment.

        :param comment_ref: reference of the comment on the social media, as
            ``get_comments`` answered it in ``remote_ref``.
        :param author_urn: actor urn whose reaction is withdrawn.
        :return: the same keys :meth:`action_like_post` answers.
        :rtype: dict
        """
        return {"success": True, "message": "", "post_deleted": False, "liked": False}

    def get_comments(self):
        """Retrieve the comments of the publication.

        Every element of ``data`` is a comment as the client draws it::

            {
                "id": "7491701601242423296",
                "remote_ref": "urn:li:comment:(urn:li:activity:749…,749…)",
                "parent_ref": False,
                "reply_count": None,
                "text": "Comment",
                "actor": "Acme Corporation",
                "author_image": "https://media.licdn.com/dms/image/…",
                "published_time": "2 weeks ago",
                "images_url": [],
                "liked": False,
            }

        ``remote_ref`` is what names the comment on the social media, and what
        travels back as the target of a reply. ``parent_ref`` is the
        ``remote_ref`` of the comment this one hangs from, ``False`` when it
        hangs from the publication itself. ``reply_count`` is how many replies
        it has, and ``None`` when the social media does not say without being
        asked for it — LinkedIn answers the comments of a post without any
        summary of their replies, so the count only arrives with
        ``get_comment_replies``.

        ``actor`` is a name to draw, never an identifier of the social media:
        a connector whose API answers only a reference resolves it before
        answering, and where it cannot --LinkedIn does not let a member be
        read-- it answers a neutral label of its own. The client draws what
        arrives, so an unresolved reference here would be shown to the user
        as it is. ``author_image`` is the URL of the picture of that actor,
        ``False`` or ``None`` when the social media reports none, and then
        the client draws a generic icon.

        ``published_time`` is the sentence :meth:`_format_published_time`
        builds, never a date: the client draws it as it arrives, so a
        connector answering the stamp of its own API would show the user a raw
        moment where every other social media says how long ago it was.

        ``liked`` is whether the account already reacted to the comment, which
        is what draws the *Recommend* entry as one thing or the other. A
        social media that does not say answers ``False``.

        :return: ``success`` and ``data`` of the action.
        :rtype: dict
        """
        return {"success": False, "data": []}

    def get_comment_replies(self, comment_ref):
        """Retrieve the replies of one comment, implemented by each connector.

        Only the connectors whose social media serves the replies apart need
        it: where the whole thread already arrives with ``get_comments``, the
        replies are nested from what is already on the client and this hook is
        never called.

        :param comment_ref: reference of the comment on the social media, as
            ``get_comments`` answered it in ``remote_ref``.
        :return: ``success``, ``data`` — the replies, shaped as the comments of
            ``get_comments`` — and ``count``, how many the social media says
            there are.
        :rtype: dict
        """
        return {"success": False, "data": [], "count": 0}

    def create_comment(self, post_data, context=None):
        """Create a comment on the social media.

        A reply is created the same way a first-level comment is: the client
        puts the ``remote_ref`` of the comment being answered in
        ``post_data["social_parent_ref"]``, and the key is simply absent when
        the comment hangs from the publication.

        A connector that can shape what it just published answers it in
        ``comment``, as one element of the list :meth:`get_comments`
        documents. The client draws that one instead of reading the thread
        again, which is what keeps a published comment from costing a second
        call against the social media. The key is left out when the answer of
        the social media does not carry enough to shape it, and then the
        client falls back to rereading the thread.

        :param post_data: message and other data of the comment.
        :param context: optional context used to render the comment.
        :return: ``success`` and ``data`` of the action, ``comment`` when the
            published comment could be shaped, plus ``post_deleted`` when the
            attempt is what revealed the publication is gone.
        :rtype: dict
        """

    def _format_published_time(self, published):
        """Return how long ago a moment is, ready to be shown to the user.

        The comments and the publications the social media answer carry the
        moment they were written, and the client draws it as "3 days ago" next
        to each one. ``_format_time_ago`` wraps
        ``babel.dates.format_timedelta``, so the text comes out in the
        language of the user and with the direction a reader expects: "3 days
        ago" rather than "3 days". The core reads it the same way for the same
        purpose in ``addons/website/models/website_visitor.py``.

        A moment is what every connector hands over, whatever shape its API
        answers with: an epoch, a stamp with an offset or none at all is the
        connector's to convert, and what reaches the client is the same
        sentence for every social media. A value without a time zone is read
        as UTC, which is what those APIs answer and what Odoo stores, and the
        delta is taken against a UTC now so that the two ends of the
        subtraction are comparable.

        A moment the social media did not say answers nothing, and the client
        then draws the comment without a date instead of one written at the
        epoch.

        :param published: the moment the content was published, as a
            ``datetime``.
        :rtype: str
        """
        if not published:
            return ""
        if not published.tzinfo:
            published = pytz.utc.localize(published)
        return _format_time_ago(self.env, datetime.now(pytz.utc) - published)

    def _get_medias_account(self, medias):
        """Return which of ``medias`` this publication already holds.

        ``medias`` are references on the social media, and the answer comes
        from ``media_refs``: the question is whether this publication has
        that media, not whether some attachment of the database carries that
        name. Two publications of the same post therefore answer for
        themselves, even when the same image gave a different reference on
        each account.

        An empty recordset holds nothing, which is what the import asks
        about a publication it has not created yet.

        :rtype: list
        """
        if not self or not medias:
            return []
        self.ensure_one()
        stored = set((self.media_refs or {}).values())
        return [media for media in medias if media in stored]

    @api.model
    def _by_remote_ref(self, refs, sudo=False, active_test=True):
        """Index the publications of these remote references by reference.

        Both bridges read the page the social media answered and have to tell
        which of its entries are already in Odoo. The two flags are what
        differs between them: LinkedIn reconciles the archived publications
        too and reads them past the record rules, X only the visible ones.

        A reference the constraint of the model already keeps unique answers
        one publication; the first one wins if a database ever holds two.

        :param refs: the remote references the social media answered.
        :param bool sudo: whether to read past the record rules.
        :param bool active_test: whether to leave the archived ones out.
        :rtype: dict
        """
        if not refs:
            return {}
        records = self.sudo() if sudo else self
        lines = records.with_context(active_test=active_test).search(
            [("remote_ref", "in", list(refs))]
        )
        return {ref: found[:1] for ref, found in lines.grouped("remote_ref").items()}

    def _store_remote_medias(self, url_by_ref):
        """Download the medias of a publication and keep what came back.

        The bridges arrive here having already left out what is stored and
        what the social media reported without a URL, so a media without one
        is skipped instead of asked for.

        The attachments come out in the order of the mapping, which is the
        order the social media listed them in: that is what the card draws.

        :param url_by_ref: ``{reference: url}``, the reference being the one
            the social media names the media by.
        :return: the attachments created and the reference of each one, keyed
            by its identifier. Both go into the same write, so that a
            downloaded media is never stored without the reference telling it
            apart from one attached in Odoo.
        :rtype: tuple
        """
        attachments = self.env["ir.attachment"]
        media_refs = {}
        for ref, url in url_by_ref.items():
            if not url:
                continue
            attachment = self._map_medias_account(name=ref, url=url)
            if attachment:
                attachments |= attachment
                media_refs[str(attachment.id)] = ref
        return attachments, media_refs

    def _map_medias_account(self, **values):
        """Download a media of the social media and attach it here.

        Nothing is created when the download fails, so that the publication
        is not left with an empty attachment the next synchronization has no
        reason to replace.

        The attachment is created here and not returned as a command, because
        its caller needs the identifier to key ``media_refs`` by it: nested in
        a command the identifier would only exist once the write it belongs to
        had run, and the reference would be lost.

        The ``url`` the media is downloaded from is required: the bridges
        skip a media the social media reported without one instead of asking
        for it here.

        :return: the attachment created, or an empty recordset on failure.
        :rtype: odoo.models.Model
        """
        Attachment = self.env["ir.attachment"]
        attach_values = values or {}
        try:
            media_content = requests.get(values["url"], timeout=10)
        except requests.exceptions.RequestException:
            _logger.warning("Could not download the media %s", values["url"])
            return Attachment
        if media_content.status_code != 200:
            _logger.warning(
                "Could not download the media %(url)s: %(status)s",
                {"url": values["url"], "status": media_content.status_code},
            )
            return Attachment
        attach_values.update(
            {
                "type": "binary",
                "res_model": self._name,
                "res_id": self.id,
                "datas": base64.b64encode(media_content.content),
            }
        )
        return Attachment.create(attach_values)
