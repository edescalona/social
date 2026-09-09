Nothing has to be configured for this module to work: it uses the LinkedIn
accounts and credentials of *Social Media Linkedin*, and the scheduled actions
of *Social Media Sync*.

It asks LinkedIn for nothing the connector does not already ask for. Reading
the feed of a page, its comments and its reactions travels on
`r_organization_social`, which *Social Media Linkedin* requests on its own,
granted by the Community Management API product that connector already needs.

What does not follow on its own is the accounts already associated. **An
access token keeps the scopes it was issued with**, so an account authorized
before that permission was requested does not hold it and its history cannot
be imported until it is authorized again. Refreshing the token is not enough:
open the account, press *Update account* with **Update keys** ticked and
authorize on LinkedIn again.

The accounts concerned say so themselves, so nothing has to be looked up: a
warning is drawn on the account form for as long as the permission is missing,
the responsible user is notified by the check that runs every two hours, and
the import refuses with the name of the missing permission instead of the bare
error LinkedIn answers.
