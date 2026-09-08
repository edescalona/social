Multi-company scope of the posts.
---------------

The accounts (`social.account`) and their daily statistics
(`social.account.statistics`) are the multi-company records: they carry a
company and a record rule that filters them. The posts and their publications
have neither a company field nor an equivalent rule, so they are only filtered
by their responsible user. In a multi-company database a social media
administrator therefore sees the posts of every company.


Limits of the social media, not of the account
---------------

The limits a post is checked against are those of the social media, not those
of the account. A paid plan can raise them — X Premium takes the message from
280 to 25 000 characters — and an account on such a plan is warned today about
a post it could publish. `_get_post_errors` already takes the account next to
the `media_type`, and the publication already passes it, so what is missing is
a connector able to tell the plan apart. Until then the checks err on the safe
side: a limit stricter than the one the account really has warns too much,
never too little, and it never blocks saving.


Figures of a card without a synchronization module
---------------

The views of a publication only draw what this module counts, so a counter no
import fills is no longer shown at zero. Two places still add up to zero on
their own: the likes and the comments printed on every card of the dashboard,
and the card of an account whose social media reports no daily figures. It is
accurate — nobody asked the social media — but it reads like a broken
dashboard, and there is no way from here to tell the two apart.


Storage of the medias of a post
---------------

The images and videos of a post and of its publications are ordinary
`ir.attachment` records, kept for as long as the record that owns them. A post
published on several accounts stores each media once, because every
publication points at the attachments of the post instead of copying them, and
what each social media made of that media is a reference in `media_refs`.

What is missing is a policy for the bytes. There is no retention: nothing ages
a media out, and the only deletions are the cascade that takes the medias of a
post or of a publication when the record itself is deleted, and
`social.account.action_purge_account`, which drops an account with its
publication history. Moving those bytes out of the filestore is not something
this module decides either: an external backend is configured at the level of
Odoo, through `ir_attachment.location`, and applies to every attachment of the
database.
