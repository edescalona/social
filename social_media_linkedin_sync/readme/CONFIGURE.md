Nothing has to be configured for this module to work: it uses the LinkedIn
accounts and credentials of *Social Media Linkedin*, and the scheduled actions
of *Social Media Sync*.

It does add one permission to what LinkedIn is asked for:
`r_organization_social`, which is what reading the publications of a page
requires. It is granted by the same Community Management API product the
connector already needs, so nothing new has to be requested from LinkedIn.

What does not follow on its own is the accounts already associated. **An
access token keeps the scopes it was issued with**, so an account authorized
before this module was installed does not hold the new permission and its
history cannot be imported until it is authorized again. Refreshing the token
is not enough: open the account, press *Update account* with **Update keys**
ticked and authorize on LinkedIn again.

The accounts concerned say so themselves, so nothing has to be looked up:
a note is posted on the chatter of each one when this module is installed, a
warning is drawn on the account form for as long as the permission is
missing, the responsible user is notified by the check that runs every two
hours, and the import refuses with the name of the missing permission instead
of the bare error LinkedIn answers.

Uninstalling this module stops LinkedIn from being asked for
`r_organization_social`: the permission is contributed by the module itself, so
it leaves with it and nothing has to be cleaned up by hand.

What does stay is the *Granted Scopes* field of the accounts already
associated, which still lists the permission. That is deliberate: the field
records what LinkedIn granted **the token currently stored**, and that token
really does hold it, so emptying the field would only make it lie. Odoo
rewrites it from LinkedIn before every publication and on the check that runs
every two hours, which would undo the change within a couple of hours anyway.

The consequence is that re-authorizing such an account asks for one permission
no installed module uses. LinkedIn grants it, since the product that does is
still enabled on the application, so nothing breaks. To make the next
authorization strictly minimal, edit *Granted Scopes* by hand and go straight
to *Update account* with **Update keys** ticked. Note that this narrows what is
requested, it does not revoke anything: the permission is withdrawn by removing
the product from the LinkedIn application, and the token keeps it until it is
replaced.
