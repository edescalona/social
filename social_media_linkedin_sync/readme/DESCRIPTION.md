This module brings back into Odoo what a LinkedIn page already published: the
posts themselves, the figures each of them collected, and their comments and
reactions.

It is the LinkedIn half of *Social Media Sync*, split from *Social Media
Linkedin* along the same line: what a call costs. The connector asks LinkedIn
for a fixed number of things per account — publish, delete, the daily figures
of the whole page — and that number does not change whether the page
published once or ten thousand times. Everything whose cost grows with the
history of the page lives here: reading the feed one page at a time, asking
for the statistics of a list of publications in chunks against the 4 KB limit
of the query string, one call per publication to check it is still there, one
call per comment thread.

An Odoo that only publishes on LinkedIn installs *Social Media Linkedin*
alone and pays for none of it.

Main features:

- Import of the publications of the page and of the statistics each of them
  collected, on demand and through the scheduled actions of *Social Media
  Sync*.
- Full resynchronization of a page, the only pass that notices a publication
  deleted on LinkedIn. Missing from the feed never marks anything on its own:
  LinkedIn is asked about each suspect by its URN, one call per hundred of
  them, and only a `404` writes the deletion. The
  [Posts API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api)
  publishes asynchronously (`PUBLISH_REQUESTED`), answers the author finder in
  reader context, and states that a page returning fewer results than asked is
  not the end of the feed — so a publication that is alive can be absent from a
  listing read whole.
- Verification that a publication still exists on LinkedIn before its thread
  is read.
- Comment threads read from the dashboard, with their replies, and *Recommend*
  on a publication and on each of its comments, which also withdraws the
  reaction it made.
- Detection of pages that moved since the last import, which turns on the
  *Update* badge of the dashboard card. It costs at most two calls per
  account, and reuses the daily figures the connector already read on the same
  pass instead of asking LinkedIn for the same days twice.
