# Copyright 2026 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.addons.social_media_linkedin.social_linkedin_utils import (
    _URN_SHARE_LINKEDIN,
    _URN_UGC_POST_LINKEDIN,
)

# The two kinds of publication ``organizationalEntityShareStatistics`` answers
# for, each one with the URN prefix that tells it apart in the feed, the query
# parameter it is asked with and the key naming it in the answer.
#
# The order matters: the two answers are merged with ``update()``, so the last
# entry is the one that wins on a URN both of them reported.
_ENTITY_STATISTICS_LINKEDIN = (
    (_URN_SHARE_LINKEDIN, "shares", "share"),
    (_URN_UGC_POST_LINKEDIN, "ugcPosts", "ugcPost"),
)

# The permission the import of the history consumes. Reading the feed of an
# organization with ``GET /rest/posts?q=author`` is what requires it, and the
# calls that follow a publication around — its social actions, its reactions
# and its comments — travel on the same one. The figures of a publication go
# with the ``rw_organization_admin`` the connector already asks for.
_SCOPE_SYNC_LINKEDIN = [
    "r_organization_social",
]

# Scopes no call of this module requires. The Community Management migration
# guide maps, since June 2023, ``r_organization_social`` to
# ``r_organization_social_feed`` and ``w_organization_social`` to
# ``w_organization_social_feed`` for the reactions and the social actions.
# That migration is about the versioned ``/rest`` resources, and the comments
# and the reactions of this module speak ``/v2``, where the permissions the
# application already holds are enough: measured against a real page on
# 2026-08-24, ``POST /rest/socialActions/{urn}/comments`` answers
# ``403 ACCESS_DENIED`` on ``partnerApiSocialActions.CREATE`` — the Partner
# Program, not a scope — while ``POST /v2/socialActions/{urn}/comments``
# publishes the comment. They are the road to follow the day ``/v2`` stops
# answering.
_SCOPE_OPTIONAL_SYNC_LINKEDIN = [
    "r_organization_social_feed",
    "w_organization_social_feed",
]

# The prefix of the URN LinkedIn names a member with. It is the actor of a
# comment that cannot be resolved into a name: the Profile API only answers
# for the authenticated member, and the token of the connector belongs to the
# organization. Comments signed by one of these are drawn with a neutral
# label, never with the name of the account reading the thread.
_URN_PERSON_LINKEDIN = "urn:li:person:"

# What is asked for of the organization behind a comment. Narrower than the
# projection the association reads, because a comment only needs the name to
# write and the logo to draw: the vanity name names nothing on screen. The
# logo travels as the URL of a playable stream and is drawn from there, so
# nothing is downloaded to show a thread.
_PROJECTION_ACTOR_LINKEDIN = "(id,name,logoV2(original~:playableStreams))"
