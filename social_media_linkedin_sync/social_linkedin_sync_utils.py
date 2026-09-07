# Copyright 2026 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

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
