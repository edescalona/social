# Copyright 2026 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
from datetime import timedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import is_list_of

from odoo.addons.social_media_linkedin.social_linkedin_utils import (
    _FINDER_PARAMS_LINKEDIN,
    _POSTS_MAX_PAGES_LINKEDIN,
    _POSTS_PAGE_SIZE_LINKEDIN,
    _UPDATE_CHECK_DAYS_LINKEDIN,
    _UPDATE_CHECK_FIGURES_LINKEDIN,
    _URL_FEED_UPDATE_LINKEDIN,
    _URN_ORGANIZATION_LINKEDIN,
    _URN_SHARE_LINKEDIN,
    _URN_UGC_POST_LINKEDIN,
    _URN_VIDEO_LINKEDIN,
    _batch_urns_by_url_size,
    datetime_from_epoch_milliseconds,
    linkedin_reaction_id,
    social_url_encode,
)

from ..social_linkedin_sync_utils import (
    _PROJECTION_ACTOR_LINKEDIN,
    _SCOPE_SYNC_LINKEDIN,
    _URN_PERSON_LINKEDIN,
)

_logger = logging.getLogger(__name__)


class SocialAccount(models.Model):
    """Import the publications of a LinkedIn page and what they collected.

    Everything here is paid by the publication, not by the account: the feed
    read page by page, the statistics asked for by URN in chunks against the
    4 KB limit of the query string. The connector keeps the daily figures of
    the whole page, which are one call whatever the history.
    """

    _inherit = "social.account"

    linkedin_missing_sync_scopes = fields.Char(
        compute="_compute_linkedin_missing_sync_scopes",
        help="The scopes the token of this account was not granted and the "
        "import of its history needs. A token keeps the scopes it was issued "
        "with, so an account associated before this module was installed has "
        "to be authorized again.",
    )
    linkedin_sync_scopes_notified = fields.Boolean(
        default=False,
        copy=False,
        help="Whether the responsible user was already told that this account "
        "has to be authorized again before its history can be imported. Kept "
        "so the check that runs every two hours warns once and not on every "
        "pass.",
    )

    linkedin_statistics_checkpoint = fields.Char(
        string="Statistics Checkpoint",
        copy=False,
        groups="base.group_system",
        help="The daily figures LinkedIn reported for the whole page over the "
        "last days, as of the last time the publications were imported. The "
        "check for updates compares the page against it instead of reading "
        "the statistics of every publication.",
    )

    @api.depends("media_id", "linkedin_granted_scopes")
    def _compute_linkedin_missing_sync_scopes(self):
        """List the scopes the token lacks and the import of the history needs.

        Computed rather than checked when a button is pressed so the account
        says what is wrong before anything is called: LinkedIn is the one
        deciding what a token gets, and it answers a token without this scope
        whenever the account was associated before this module existed.
        """
        for account in self:
            if account.media_id.media_type != "linkedin":
                account.linkedin_missing_sync_scopes = ""
                continue
            account.linkedin_missing_sync_scopes = ", ".join(
                account._missing_linkedin_scopes(_SCOPE_SYNC_LINKEDIN)
            )

    def _get_all_posts(self):
        """Read the whole feed of the account, page by page.

        A single page is not the feed: LinkedIn documents that a page may
        carry fewer posts than asked while more are left, so the end is only
        reached on an empty page. Knowing whether the end was reached is what
        makes it safe to conclude that a post missing from the answer was
        deleted, hence the flag returned along the posts.

        :return: the posts of the account and whether the feed was read whole.
        :rtype: tuple(list, bool)
        """
        self.ensure_one()
        posts = []
        seen_urns = set()
        for page in range(_POSTS_MAX_PAGES_LINKEDIN):
            page_posts = self._get_posts(
                params_fields=["start"],
                params_values={"start": page * _POSTS_PAGE_SIZE_LINKEDIN},
                add_values=True,
            )
            if not page_posts:
                return posts, True
            for post in page_posts:
                if post["id"] not in seen_urns:
                    seen_urns.add(post["id"])
                    posts.append(post)
        _logger.warning(
            "The feed of the LinkedIn account %s is longer than %s pages, it "
            "was read partially and the deleted posts are not looked for",
            self.name,
            _POSTS_MAX_PAGES_LINKEDIN,
        )
        return posts, False

    def _query_string_bytes(self, params_fields, params_values):
        """Return what the given query parameters weigh once encoded.

        Tells how much room is left for the URNs of a statistics call, the
        only part of the query string that can be split.

        :rtype: int
        """
        return sum(
            len(social_url_encode(param_field, params_values).encode())
            # The "&" joining this parameter to the next one.
            + 1
            for param_field in params_fields
        )

    def _filter_urns(self, posts, urn_prefix):
        """Return the URNs of the posts of one kind, in the order given.

        :param posts: the posts as the Posts API answered them.
        :param urn_prefix: ``urn:li:share:`` or ``urn:li:ugcPost:``.
        :rtype: list
        """
        return [
            post["id"]
            for post in posts
            if post.get("id") and post["id"].startswith(urn_prefix)
        ]

    def _parse_share_statistics(self, payload, urn_key):
        """Read the answer of ``organizationalEntityShareStatistics``.

        The shares and the UGC posts are asked for with a parameter of their
        own but answer the very same block, only the key naming the entity
        changes. An entity with no activity at all is left out of the answer,
        and is therefore left out of the result: its figures are all zero.

        :param payload: the parsed answer of LinkedIn.
        :param urn_key: ``share`` or ``ugcPost``.
        :return: Statistics tuple by post URN.
        :rtype: dict
        """
        statistics = {}
        for element in payload.get("elements", []):
            urn = element.get(urn_key)
            if not urn:
                continue
            totals = element.get("totalShareStatistics", {})
            statistics[urn] = (
                totals.get("clickCount", 0),
                totals.get("likeCount", 0),
                totals.get("commentCount", 0),
                totals.get("shareCount", 0),
                totals.get("engagement", 0),
                totals.get("impressionCount", 0),
            )
        return statistics

    def _get_entity_share_statistics(
        self,
        urns,
        param_field,
        urn_key,
        error_label,
        params_fields=None,
        params_values=None,
    ):
        """Read ``organizationalEntityShareStatistics`` for the given URNs.

        LinkedIn takes every URN in the query string and documents that
        endpoint as not paginated, so the URNs are split into as many calls
        as the 4 KB limit of the query string needs.

        :param urns: the URNs to read the statistics of.
        :param param_field: ``shares`` or ``ugcPosts``.
        :param urn_key: the key naming the entity in the answer.
        :param error_label: what to call the call in the error message.
        :return: Statistics tuple by post URN.
        :rtype: dict
        """
        data = {}
        params_fields = list(params_fields or [])
        params_values = dict(params_values or {})
        fixed_bytes = self._query_string_bytes(params_fields, params_values)
        for batch in _batch_urns_by_url_size(urns, param_field, fixed_bytes):
            response = self._request_linkedin(
                endpoint="/organizationalEntityShareStatistics",
                headers=self.media_id._get_linkedin_headers(
                    access_token=self.sudo().access_token, x_restli_method="FINDER"
                ),
                params_fields=params_fields + [param_field],
                params_values={**params_values, param_field: [",".join(batch)]},
                linkedin_v2=True,
                return_json=False,
            )
            if response.status_code != 200:
                raise UserError(
                    _(
                        "%(label)s: %(error)s",
                        label=error_label,
                        error=self._linkedin_error_message(response),
                    )
                )
            data.update(self._parse_share_statistics(response.json(), urn_key))
        return data

    def _get_share_statistics(
        self,
        posts=None,
        params_fields=None,
        params_values=None,
    ):
        """Read the statistics of the share posts among the given ones.

        :return: Statistics tuple by share URN.
        :rtype: dict
        """
        if not posts:
            return {}
        return self._get_entity_share_statistics(
            self._filter_urns(posts, _URN_SHARE_LINKEDIN),
            "shares",
            "share",
            _("The statistics of the shared publications could not be read"),
            params_fields=params_fields,
            params_values=params_values,
        )

    def _get_ugc_share_statistics(
        self,
        posts=None,
        params_fields=None,
        params_values=None,
    ):
        """Read the statistics of the UGC posts among the given ones.

        Same endpoint as the shares, asked with the ``ugcPosts`` parameter.
        It is what brings the clicks, the shares, the engagement and the
        impressions of a UGC post: ``socialActions`` only knows its likes and
        its comments.

        :return: Statistics tuple by UGC post URN.
        :rtype: dict
        """
        if not posts:
            return {}
        return self._get_entity_share_statistics(
            self._filter_urns(posts, _URN_UGC_POST_LINKEDIN),
            "ugcPosts",
            "ugcPost",
            _("The statistics of the publications could not be read"),
            params_fields=params_fields,
            params_values=params_values,
        )

    def _get_ugc_posts_statistics(
        self,
        posts=None,
        params_fields=None,
        params_values=None,
    ):
        """Read the likes and the comments of the UGC posts of the feed.

        LinkedIn documents ``socialActions`` as the up-to-date source of
        those two counts, the ones the feed shows, which is why they are read
        apart from the rest of the figures. It is asked for in as many calls
        as the 4 KB limit of the query string needs.

        :return: ``(likes, comments)`` by UGC post URN.
        :rtype: dict
        """
        data = {}
        if not posts:
            return data
        params_fields = list(params_fields or [])
        params_values = dict(params_values or {})
        fixed_bytes = self._query_string_bytes(params_fields, params_values)
        urns = self._filter_urns(posts, _URN_UGC_POST_LINKEDIN)
        for batch in _batch_urns_by_url_size(urns, "ids", fixed_bytes):
            response = self._request_linkedin(
                endpoint="/socialActions",
                headers=self.media_id._get_linkedin_headers(
                    access_token=self.sudo().access_token
                ),
                params_fields=params_fields + ["ids"],
                params_values={**params_values, "ids": [",".join(batch)]},
                return_json=False,
                linkedin_v2=True,
            )
            if response.status_code != 200:
                raise UserError(
                    _(
                        "The likes and the comments of the publications could not be "
                        "read: %(error)s",
                        error=self._linkedin_error_message(response),
                    )
                )
            data.update(
                {
                    urn_id: (
                        post_reaction.get("likesSummary", {}).get("totalLikes", 0),
                        post_reaction.get("commentsSummary", {}).get(
                            "aggregatedTotalComments", 0
                        ),
                    )
                    for urn_id, post_reaction in response.json()
                    .get("results", {})
                    .items()
                }
            )
        return data

    def _get_reactions(self, entities):
        """Read which of the given entities the account already reacted to.

        The Reactions API addresses a reaction by the pair that creates it,
        so one batch answers a whole page of publications. Asking one by one
        would cost a call per publication, which is the kind of price this
        module exists to avoid.

        Not knowing is told apart from not having reacted: the answer is
        ``None`` when LinkedIn could not be read, and the caller leaves what
        it draws untouched instead of clearing it. A partial reading is
        thrown away for the same reason --the entities of the batch that
        failed would look unreacted-- so any failure discards the whole pass.

        :param entities: URNs of the shares, UGC posts or comments to ask
            about.
        :return: the URNs among them this account holds a reaction on, or
            ``None`` when LinkedIn did not answer.
        :rtype: set or None
        """
        self.ensure_one()
        actor = self.remote_ref
        asked = [entity for entity in dict.fromkeys(entities or []) if entity]
        if not actor or not asked:
            return set()
        reacted = set()
        keys = [linkedin_reaction_id(actor, entity) for entity in asked]
        for batch in _batch_urns_by_url_size(keys, "ids"):
            try:
                response = self._request_linkedin(
                    endpoint="/reactions",
                    headers=self.media_id._get_linkedin_headers(
                        access_token=self.sudo().access_token
                    ),
                    params_fields=["ids"],
                    params_values={"ids": [",".join(batch)]},
                    return_json=False,
                    linkedin_v2=True,
                )
            except UserError:
                # Which reactions are the account's own is not worth losing an
                # import over: the figures are what the pass is for, and the
                # entry of the card is drawn as it was.
                _logger.warning(
                    "LinkedIn could not be reached for the reactions of the "
                    "account %s",
                    actor,
                )
                return None
            if response.status_code != 200:
                _logger.warning(
                    "The reactions of the LinkedIn account %s could not be " "read: %s",
                    actor,
                    response.status_code,
                )
                return None
            # Keyed by the very key that was asked for, percent-encoded the
            # way LinkedIn chose to echo it. The entity is read from ``root``
            # instead, which travels plain.
            reacted.update(
                reaction["root"]
                for reaction in response.json().get("results", {}).values()
                if reaction.get("root")
            )
        return reacted

    def _linkedin_reaction_values(self, entity, reacted):
        """What to write on a publication about the reaction of the account.

        :param entity: URN of the publication.
        :param reacted: the URNs the account reacted to, or ``None`` when
            LinkedIn did not answer.
        :return: the values to write, empty when nothing is known.
        :rtype: dict
        """
        if reacted is None or not entity:
            return {}
        return {"liked_by_account": entity in reacted}

    def _get_linkedin_actors(self, urns):
        """Resolve the actors of a thread into the name and picture to draw.

        Only the organizations can be asked about. The Profile API answers
        for the authenticated member and no other, and the token of the
        connector belongs to the page, so a person is dropped before the
        call: there is nothing to ask for. The account itself is dropped for
        the opposite reason, its name and its avatar are already in Odoo.

        One call per distinct organization, which is why the URNs of the
        whole batch arrive together: a thread has as many comments as it has,
        but few organizations behind them.

        A name is never worth a thread. An organization LinkedIn refuses --a
        ``403`` is what one the account does not administer answers-- is
        logged and left out of the result, and the caller draws it with a
        neutral label. Nothing raises out of here.

        :param urns: what LinkedIn named the actors of the comments with,
            repetitions included and the dict a comment with no stamp
            carries among them.
        :return: ``{urn: {"name": str, "image": str or False}}``, holding
            only the organizations that answered a name.
        :rtype: dict
        """
        self.ensure_one()
        # Filtered before being deduplicated: a comment LinkedIn stamped
        # with nothing carries a dict where the URN goes, and a dict cannot
        # be a key.
        asked = dict.fromkeys(
            urn
            for urn in urns or []
            if isinstance(urn, str)
            and urn
            and urn != self.remote_ref
            and not urn.startswith(_URN_PERSON_LINKEDIN)
        )
        if not asked:
            return {}
        headers = self.media_id._get_linkedin_headers(
            access_token=self.sudo().access_token
        )
        actors = {}
        for urn in asked:
            try:
                response = self._request_linkedin(
                    endpoint=f"/organizations/{urn.split(':')[-1]}",
                    linkedin_v2=True,
                    headers=headers,
                    params={"projection": _PROJECTION_ACTOR_LINKEDIN},
                )
            except UserError:
                _logger.info("LinkedIn could not be reached for the actor %s", urn)
                continue
            if not isinstance(response, dict):
                _logger.info(
                    "The LinkedIn actor %s could not be read: %s",
                    urn,
                    getattr(response, "status_code", response),
                )
                continue
            # The organization publishes its name in several languages: the
            # one of the user is preferred, and any of them is taken rather
            # than drawing the comment with no name at all.
            localized = response.get("name", {}).get("localized", {})
            name = (
                localized.get(self.env.user.lang)
                or localized.get("en_US")
                or next(iter(localized.values()), "")
            )
            if not name:
                continue
            actors[urn] = {
                "name": name,
                "image": self._get_linkedin_actor_image(response),
            }
        return actors

    def _get_linkedin_actor_image(self, organization):
        """Return the URL of the logo of an organization, largest first.

        The URL of a playable stream, not the bytes behind it: the logo of an
        actor is only drawn while the dialog of the thread is open, so
        nothing is downloaded and nothing is stored. That is what tells this
        apart from ``_get_linkedin_organization_logo``, which does download
        the logo because it becomes the avatar of the account.

        :param organization: the organization as the Organizations API
            answered it.
        :return: the URL of the logo, ``False`` when LinkedIn reported none.
        :rtype: str or bool
        """
        elements = (
            organization.get("logoV2", {}).get("original~", {}).get("elements", [])
        )
        if not elements:
            return False
        preferred = [
            element
            for element in elements
            if "logo_400_400" in element.get("artifact", "")
        ] or elements
        identifiers = preferred[0].get("identifiers", [])
        return identifiers[0].get("identifier", False) if identifiers else False

    def _get_entity_statistics(
        self,
        posts=None,
        params_fields=None,
        params_values=None,
    ):
        """Merge the statistics of the share posts and of the UGC posts.

        Three calls are needed. ``organizationalEntityShareStatistics``
        answers the whole block of figures, but the shares and the UGC posts
        are asked for with a parameter of their own. ``socialActions`` is
        read on top of it because LinkedIn documents its likes and its
        comments as the up-to-date ones, the ones the feed shows.

        :return: Statistics tuple by post URN.
        :rtype: dict
        """
        if self.media_type != "linkedin":
            return {}
        if not posts:
            return {}
        if not params_fields:
            params_fields = ["q", "organizationalEntity"]
        if not params_values:
            params_values = {
                "q": "organizationalEntity",
                "organizationalEntity": f"{_URN_ORGANIZATION_LINKEDIN}"
                f"{self.linkedin_account_id}",
            }
        entity_params = {
            "params_fields": list(params_fields),
            "params_values": dict(params_values),
        }
        data = self._get_share_statistics(posts=posts, **entity_params)
        data.update(self._get_ugc_share_statistics(posts=posts, **entity_params))
        # ``socialActions`` takes neither the criteria of the share finder
        # nor the organization it is about.
        social_actions = self._get_ugc_posts_statistics(
            posts=posts,
            params_fields=[
                param_field
                for param_field in params_fields
                if param_field not in _FINDER_PARAMS_LINKEDIN
            ],
            params_values={
                key: value
                for key, value in params_values.items()
                if key not in _FINDER_PARAMS_LINKEDIN
            },
        )
        for urn, (likes, comments) in social_actions.items():
            clicks, __, __, shares, engagement, impressions = data.get(
                urn, (0, 0, 0, 0, 0, 0)
            )
            data[urn] = (clicks, likes, comments, shares, engagement, impressions)
        return data

    def _update_posts_statistics(self, post_id, domain, imported=None):
        statistics = super()._update_posts_statistics(post_id, domain, imported)
        account_ids = self._accounts_of_media("linkedin")
        if self and not account_ids:
            # Asked for accounts, none of them LinkedIn's: what the other
            # connectors answered goes back untouched.
            return statistics
        for account in account_ids:
            with account._statistics_guard():
                account._import_linkedin_posts(post_id=post_id)
                # Inside the guard on purpose: an account it rolls back never
                # reaches this line, which is what tells a feed that was read
                # from one LinkedIn refused.
                account._report_imported(imported)
        return self._get_account_statistics(statistics=statistics)

    def _full_resync(self):
        """Read the whole feed of the LinkedIn accounts and reconcile it.

        The whole feed page by page, and not the single page the ordinary
        refresh reads. It is kept apart because a feed of thousands of
        publications costs one call per hundred, and the only thing that needs
        all of it is reconciling what was deleted on LinkedIn: the statistics
        are asked for by URN and Odoo already knows the URNs.

        :return: whatever the other connectors answer for their own accounts.
        """
        linkedin = self.filtered(lambda account: account.media_type == "linkedin")
        for account in linkedin:
            with account._statistics_guard():
                account._import_linkedin_posts(full_feed=True)
        return super(SocialAccount, self - linkedin)._full_resync()

    def _import_linkedin_posts(self, post_id=None, full_feed=False, buckets=None):
        """Import the publications of this account and their statistics.

        Three ways in, and what the feed is read for is what tells them apart:

        - ``post_id``: one publication, asked for by its URN.
        - ``full_feed``: the whole feed, page by page, which is the only way to
          know that a publication was deleted on LinkedIn.
        - neither: the ordinary refresh. **The feed is not walked.** One page
          sorted by last modification brings what is new or edited, and the
          statistics are asked for by URN over that page plus the URNs Odoo
          already stores for the account. A publication whose content did not
          change does not need to be read again: nothing can change it without
          LinkedIn moving its last modification date.

        :param post_id: the URN of the only publication to refresh.
        :param full_feed: whether to walk the whole feed and reconcile it.
        :param buckets: the RAW buckets --the six figures per day-- the daily
            sweep of this very pass already read, so the finder is not asked
            twice for the same days. ``None`` means read them here, so a
            standalone import still leaves a valid mark. Never the trimmed
            form: the trimming to the five watched figures is done here, and
            a mark written from an already trimmed reading compares wrong for
            good.
        """
        self.ensure_one()
        # Before the token is even validated: a call that cannot succeed is
        # better refused with the name of the permission it needs than with
        # the bare 403 LinkedIn answers.
        self._check_linkedin_scopes(_SCOPE_SYNC_LINKEDIN)
        PostAccount = self.env["social.post.account"]
        self.with_context(not_notify=True).validate_access_token()
        if not self.linkedin_account_id:
            return
        feed_is_complete = False
        if post_id:
            ugc_posts = self._get_posts(
                params_fields=["ids"], params_values={"ids": [post_id]}
            )
        elif full_feed:
            ugc_posts, feed_is_complete = self._get_all_posts()
        else:
            # Fresh literals: with ``add_values`` the finder parameters are
            # merged into the given ones in place.
            ugc_posts = self._get_posts(
                params_fields=["sortBy"],
                params_values={"sortBy": "LAST_MODIFIED"},
                add_values=True,
            )
        discovered = [post["id"] for post in ugc_posts if post.get("id")]
        # A post missing from the answer is only gone when the whole feed was
        # read: on a partial answer the same search would mark live
        # publications as deleted.
        if feed_is_complete:
            PostAccount.search(
                [
                    ("remote_ref", "not in", discovered),
                    ("remote_ref", "!=", False),
                    ("account_id", "=", self.id),
                    ("state", "!=", "deleted"),
                ]
            ).write({"post_account_url": False, "state": "deleted"})
        # The publications Odoo knows and the answer did not bring. Their
        # figures are refreshed all the same, by URN, which is what spares
        # reading the feed. ``sudo`` because the publications are scoped to
        # their responsible and this also runs from a cron, and ``active_test``
        # off because an archived publication is still online on LinkedIn.
        stale_lines = PostAccount
        if not post_id:
            stale_lines = (
                PostAccount.sudo()
                .with_context(active_test=False)
                .search(
                    [
                        ("account_id", "=", self.id),
                        ("remote_ref", "!=", False),
                        ("remote_ref", "not in", discovered),
                        ("state", "!=", "deleted"),
                    ]
                )
            )
        refreshed_urns = discovered + stale_lines.mapped("remote_ref")
        post_reactions = self._get_entity_statistics(
            posts=[{"id": urn} for urn in refreshed_urns]
        )
        # Whether the account itself reacted is not part of the figures: it is
        # what the *Recommend* entry of the dashboard draws, and one batch
        # answers it for the whole page.
        own_reactions = self._get_reactions(refreshed_urns)
        post_accounts = []
        post_accounts_by_urn = PostAccount._by_remote_ref(
            discovered, sudo=True, active_test=False
        )
        for ugc_post in ugc_posts:
            post_account = post_accounts_by_urn.get(ugc_post.get("id"), PostAccount)
            content = ugc_post.get("content", {})
            ugc_post_urn = ugc_post.get("id")
            data = {
                "remote_ref": ugc_post_urn,
                "post_account_url": f"{_URL_FEED_UPDATE_LINKEDIN}{ugc_post_urn}",
                "message": ugc_post.get("commentary", ""),
                "account_id": self.id,
                # LinkedIn dates the publication in epoch milliseconds, and a
                # feed it answers without one is stored as read now: the
                # publication exists, only its moment is missing.
                "published_date": (
                    datetime_from_epoch_milliseconds(ugc_post["publishedAt"])
                    if ugc_post.get("publishedAt")
                    else fields.Datetime.now()
                ),
                "actor_urn": ugc_post.get("author", False),
                "has_video": str(content.get("media", {}).get("id", "")).startswith(
                    _URN_VIDEO_LINKEDIN
                ),
                "state": "posted",
                **self._linkedin_statistics_values(post_reactions.get(ugc_post_urn)),
                **self._linkedin_reaction_values(ugc_post_urn, own_reactions),
            }
            attach_images, media_refs = post_account._get_assets_save(
                content, account=self
            )
            if post_account:
                post_account._remove_assets_deleted(content)
            post_accounts.append(
                self._import_command(post_account, data, attach_images, media_refs)
            )
        for line in stale_lines:
            post_accounts.append(
                Command.update(
                    line.id,
                    {
                        **self._linkedin_statistics_values(
                            post_reactions.get(line.remote_ref)
                        ),
                        **self._linkedin_reaction_values(
                            line.remote_ref, own_reactions
                        ),
                    },
                )
            )
        update_account_data = {
            "post_account_ids": post_accounts,
        }
        # The check for updates compares the daily figures of the page against
        # the ones of the last import, so the import is what leaves the mark to
        # compare with. Refreshing a single publication says nothing about the
        # rest of the page.
        if not post_id:
            if buckets is None:
                buckets = self._linkedin_read_watched_figures()
            else:
                buckets = self._linkedin_watched_figures(buckets)
            update_account_data[
                "linkedin_statistics_checkpoint"
            ] = self._linkedin_statistics_checkpoint(buckets)
        self.write(update_account_data)
        # Through the method of the flag and not as one more key of the write:
        # it is what pushes the notice down on the dashboards already open,
        # and this import is also reached from the full resync, which never
        # goes through ``update_posts_statistics``.
        self._clear_posts_need_import()

    def _get_account_statistics(self, statistics=None):
        return self._media_statistics_payload(
            "linkedin", statistics, extra_fields=("account_url",)
        )

    def _linkedin_read_watched_figures(self):
        """Ask LinkedIn for the figures the update check compares.

        Asked with ``timeIntervals`` and no URN, the endpoint answers one
        bucket per day covering the whole organization instead of one entry per
        publication. That is one call whatever the number of publications,
        which is what makes it worth watching to know whether anything moved.

        The daily buckets are watched instead of the lifetime totals the same
        endpoint answers without ``timeIntervals``, because those totals lag
        behind. Verified against the real account: a reaction given an hour and
        a half earlier was already counted in the buckets while the lifetime
        figures still ignored it, and the sum of the twelve monthly buckets
        matched the lifetime answer to the unit on every figure except that one
        reaction. The lifetime totals are therefore useless as a signal of
        freshness, whatever else they are good for.

        Those figures are not the sum of what Odoo imported and are not meant
        to be compared against it: LinkedIn counts publications older than the
        import and stops counting the ones that were deleted. They are only
        ever compared against the previous reading of themselves.

        Only the import needs to ask: the check of the cron reads the buckets
        the refresh sweep of its own pass already brought back. The window is
        the one the sweep reads, trimmed to the days the check compares, so
        the mark left here is the one that pass would have left.

        :return: the watched figures by day, empty when LinkedIn reports none.
        :rtype: dict
        """
        self.ensure_one()
        start_time, end_time = self._linkedin_statistics_interval(
            *self._linkedin_refresh_window()
        )
        return self._linkedin_watched_figures(
            self._get_linkedin_daily_statistics(start_time, end_time, "DAY")
        )

    @api.model
    def _linkedin_check_days(self):
        """Return the ISO days the update check compares, today included.

        ``_UPDATE_CHECK_DAYS_LINKEDIN`` days counting today, keyed the same
        way ``_get_linkedin_daily_statistics`` keys its buckets so the two can
        be intersected without converting anything.

        This window is one day narrower than the one the refresh rewrites, and
        deliberately so: the checkpoints already stored were written with these
        days, and comparing them against a wider set would read the extra day
        as a day that appeared with activity, flagging every active account at
        once on the first pass after deploying.

        :rtype: set
        """
        today = fields.Date.today()
        return {
            (today - timedelta(days=offset)).isoformat()
            for offset in range(_UPDATE_CHECK_DAYS_LINKEDIN)
        }

    @api.model
    def _linkedin_watched_figures(self, buckets):
        """Return the watched figures of the days the check compares.

        Trims the buckets to ``_linkedin_check_days`` and keeps only
        ``_UPDATE_CHECK_FIGURES_LINKEDIN`` out of each one: the engagement is
        left out because it is a ratio LinkedIn recomputes, so it moves
        without anything having happened on the page.

        Pure on purpose: the figures come from the buckets the refresh of the
        same pass already brought back, so the check compares what it needs
        without asking LinkedIn for anything of its own.

        :param buckets: the buckets as ``_get_linkedin_daily_statistics``
            builds them, keyed by ISO day.
        :return: the watched figures by day, empty when there are none.
        :rtype: dict
        """
        days = self._linkedin_check_days()
        return {
            day: tuple(figures[index] for index in _UPDATE_CHECK_FIGURES_LINKEDIN)
            for day, figures in (buckets or {}).items()
            if day in days
        }

    @api.model
    def _linkedin_statistics_checkpoint(self, statistics):
        """Return the stored form of the daily buckets of a page.

        Kept as sorted JSON so the value is stable whatever order LinkedIn
        answered the buckets in.

        :param statistics: the buckets as ``_linkedin_watched_figures`` returns
            them, keyed by the ISO day. A string and never a ``date``: this very
            dictionary travels through ``json.dumps``, so changing the key
            invalidates every checkpoint already stored.
        :return: the value to store, empty when there is nothing to compare.
        :rtype: str
        """
        if not statistics:
            return ""
        return json.dumps(
            {period: list(figures) for period, figures in statistics.items()},
            sort_keys=True,
        )

    @api.model
    def _linkedin_statistics_snapshot(self, checkpoint):
        """Read back a checkpoint, ignoring anything that is not one.

        The value comes from a stored column, so it is validated instead of
        trusted: a checkpoint written by an older version of this check, or edited
        by hand, must read as "no baseline yet" rather than compare wrongly.

        :param checkpoint: the stored value.
        :return: the buckets by day, empty when there is nothing usable.
        :rtype: dict
        """
        if not checkpoint:
            return {}
        try:
            snapshot = json.loads(checkpoint)
        except ValueError:
            return {}
        if not isinstance(snapshot, dict):
            return {}
        return {
            period: figures
            for period, figures in snapshot.items()
            if is_list_of(figures, (int, float))
        }

    @api.model
    def _linkedin_statistics_moved(self, previous, current):
        """Tell whether the daily buckets carry activity the last import missed.

        Buckets are compared day by day and never as a whole: the window slides,
        so the oldest day of the previous reading is gone from this one, and
        comparing the two sets would report a change every single day.

        A day missing from the previous reading only counts when it carries
        activity. LinkedIn answers a bucket of zeros for a day with nothing on it,
        and the day in progress starts as one of those: announcing it would mean
        announcing updates every midnight.

        A day gone from this reading is ignored: it aged out of the window, which
        is not activity.

        :param previous: the buckets of the last import.
        :param current: the buckets read now.
        :return: whether anything moved.
        :rtype: bool
        """
        if not previous:
            return False
        for period, figures in current.items():
            stored = previous.get(period)
            if stored is None:
                if any(figures):
                    return True
            elif list(stored) != list(figures):
                return True
        return False

    def _check_linkedin_updates(self, buckets):
        """Flag this account when its page moved since the last import.

        :param buckets: the buckets the refresh sweep of this pass read for
            this account, as ``_get_linkedin_daily_statistics`` builds them.
        :return: whether the account was flagged.
        :rtype: bool
        """
        self.ensure_one()
        statistics = self._linkedin_watched_figures(buckets)
        previous = self._linkedin_statistics_snapshot(
            self.linkedin_statistics_checkpoint
        )
        if not previous:
            # Nothing to compare with yet, on an account associated before this
            # check knew how to. Reading the page is what gives it its mark:
            # announcing updates on the very first run would announce them for
            # every account at once.
            self.linkedin_statistics_checkpoint = self._linkedin_statistics_checkpoint(
                statistics
            )
            return False
        if self._linkedin_statistics_moved(previous, statistics):
            # The mark is left alone on purpose: it belongs to the last
            # import, so the notice stays up until the user actually imports
            # instead of clearing itself on the next run.
            self._flag_linkedin_update()
            return True
        # The figures did not move, but a publication posted outside Odoo that
        # nobody has interacted with yet does not move them either.
        post_ids = self._get_posts(
            params_fields=["sortBy"],
            params_values={"sortBy": "LAST_MODIFIED"},
            add_values=True,
        )
        if not post_ids:
            return False
        # ``sudo`` because the publications are scoped to their responsible and
        # this also runs from the cron, and ``active_test`` off because
        # archiving a post archives its publications while they stay online on
        # LinkedIn: an archived row is known, not new.
        known = (
            self.env["social.post.account"]
            .sudo()
            .with_context(active_test=False)
            .search_count(
                [
                    ("remote_ref", "=", post_ids[0]["id"]),
                    ("remote_ref", "!=", False),
                    ("account_id", "=", self.id),
                ],
                limit=1,
            )
        )
        if known:
            return False
        self._flag_linkedin_update()
        return True

    def _notify_missing_sync_scopes(self):
        """Tell the user in charge that the account cannot import its history.

        Addressed with ``partner_ids`` rather than left on the chatter: the
        one running into the broken account is the check that runs every two
        hours, so the note has to reach the Inbox of whoever owns it without
        anybody opening the account.

        ``posts_need_import`` is deliberately not turned on.
        :meth:`_linkedin_check_updates` skips every account carrying it, so an
        account flagged here would never be checked again: only the import
        takes the flag down, and the import is the very thing that cannot run.
        """
        self.ensure_one()
        if self.linkedin_sync_scopes_notified:
            return
        self.sudo().write({"linkedin_sync_scopes_notified": True})
        self.message_post(
            body=_(
                "The token of this account was not granted %(scopes)s, so "
                "LinkedIn refuses to serve its publications and they cannot "
                "be imported. Enable the matching product on the LinkedIn "
                "application, then press Update account with Update keys "
                "checked to authorize this account again: refreshing the "
                "token alone keeps the scopes it already has.",
                scopes=self.linkedin_missing_sync_scopes,
            ),
            partner_ids=self.user_id.partner_id.ids,
        )

    def _on_account_associated(self):
        """Let a re-authorization that still lacks the scope warn again.

        Every association passes through here, and none of them can be trusted
        to have brought the scope: the LinkedIn application may simply not have
        the product that grants it. Clearing the mark is what makes the next
        pass of the check look again and tell the user a second time, which is
        better than going quiet on an account that is still broken.
        """
        self.sudo().filtered(
            lambda account: account.media_type == "linkedin"
        ).linkedin_sync_scopes_notified = False
        return super()._on_account_associated()

    def _detects_pending_posts(self):
        """LinkedIn says the page moved without the publications being read.

        One call per account against the share statistics of the whole page,
        which is what :meth:`_linkedin_check_updates` compares: an account
        whose figures did not move is known to have nothing to import, so the
        *Update* button is free to leave it alone.

        :rtype: bool
        """
        self.ensure_one()
        if self.media_type != "linkedin":
            return super()._detects_pending_posts()
        return True

    def _flag_linkedin_update(self):
        """Announce on the dashboard that the account has updates to import.

        The state is ``posts_need_import`` and not ``need_update``: the latter
        says that the credentials expired, which asks the user for a new
        authorization instead of for an import, and an account whose token
        works is exactly the one that has publications to bring in.
        """
        self.ensure_one()
        self._flag_posts_need_import()

    def _linkedin_check_updates(self, buckets_by_account):
        """Flag the accounts whose page moved since the last import.

        At most one extra call per account, and only where the figures did not
        move: a change in them is enough to know that something happened and
        spares asking the feed for its newest publication, which is what
        catches a post published outside Odoo that nobody has interacted with
        yet.

        The check never imports anything: it only turns on
        ``posts_need_import``, and the import the user asks for is what turns
        it off and leaves the new figures to compare with.

        Two kinds of account are skipped and cost no call at all. One already
        announcing updates: only the import clears ``posts_need_import``, so
        asking LinkedIn again before the user imports can only confirm what
        the dashboard already says. And one whose credentials expired: a call
        made with a token that is known to be dead is spent to arrive at a
        ``SocialCredentialsError``, and what that account is waiting for is a
        new authorization, not an import.

        That is why it is a ``filtered`` over what the sweep walked and not a
        search of its own: the sweep is the wider of the two, so every account
        reached here already has its buckets read, by construction rather than
        by an agreement between two domains.

        :param buckets_by_account: ``{account.id: buckets}`` as
            ``_linkedin_refresh_statistics`` returns them, the SIX raw figures
            per day. The trimming to the five watched ones happens in
            ``_check_linkedin_updates``.
        :return: whether any account was flagged, this pass or before.
        :rtype: bool
        """
        update = super()._linkedin_check_updates(buckets_by_account)
        for account in self.filtered(
            lambda account: not account.posts_need_import and not account.need_update
        ):
            if account.linkedin_missing_sync_scopes:
                # Nothing to check: the import this would announce cannot run.
                # The responsible user is told instead of the log, which is
                # what nobody reads when a cron writes it.
                account._notify_missing_sync_scopes()
                continue
            buckets = buckets_by_account.get(account.id)
            if buckets is None:
                # The sweep failed on this account: its savepoint was rolled
                # back and its responsible user already told, so asking again
                # here would only fail again. The next pass retries it two
                # hours later.
                continue
            # Each account in its own savepoint: the check writes, so a
            # database error on one of them would otherwise abort the cursor
            # and take down every account left, including the credentials the
            # base already flagged.
            with account._account_guard(
                "Error checking the updates of the LinkedIn account %s"
            ):
                update = account._check_linkedin_updates(buckets) or update
        return update
