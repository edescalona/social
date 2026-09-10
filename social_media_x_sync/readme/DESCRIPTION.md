This module brings back into Odoo what an X account already published: the
posts of its timeline, the figures each of them collected, and their comments.

It is the X half of *Social Media Sync*, split from *Social Media X* along the
same line: what a call costs. The connector asks X for a fixed number of
things per account — link it, refresh its card, publish, delete, read the
figures of the publications of the last 30 days — and that number does not
change whether the account published once or ten thousand times. Everything whose cost grows with the history of the account lives here:
the timeline that answers up to a hundred publications and one download per
media not stored yet, one call per publication whose comments are read, and
one call per publication that is verified.

An Odoo that only publishes on X installs *Social Media X* alone and pays for
none of it.

Main features:

- Import of the publications of the timeline and of the figures each of them
  collected, on demand and through the scheduled actions of *Social Media
  Sync*.
- Comments of a publication, read from the dashboard: the conversation is
  walked page by page up to a ceiling, and the replies of a comment are nested
  from what was read instead of being asked for apart. A comment answers the
  publication, and answering a comment answers that comment, which on X is a
  post like any other.
- Verification that a publication still exists on X before the dashboard acts
  on it.
- Reading only what was published after a chosen publication, with *Enable
  since*, for an account that does not need its whole history read again.

*Recommend* is not offered on X, neither on a publication nor on a comment.
X does serve the endpoints — `POST /2/users/:id/likes` and
`DELETE /2/users/:id/likes/:tweet_id`, and a comment is a post like any other,
so both would be the same call — but it
[withdrew their access from the Free tier](https://devcommunity.x.com/t/update-to-x-api-free-tier-removal-of-like-and-follow-endpoints/247646).
This module does not implement them, and until it does the button is not
rendered for the X publications. The roadmap says the rest.

Statistics account
-------------------
In the case of X statistics, only current posts are taken into account; if
some are deleted, the metrics also decrease, that is, it is not a
history of the account's posts.

The metrics are computed on the **100 most recent publications** X answers in
a single request, and only on original publications: retweets, replies and
quotes are discarded both when importing and when computing. The publications
older than those 100 are not counted, because the timeline
(`GET /2/users/:id/tweets`) is read once and not paginated, in order to spare
the requests of the plan.

1. The eye icon: Total number of views, which may include multiple views by the same user.
2. The hand icon: means the interactions (likes, comments, retweets and quotes)
   of current posts. They are the
   [metrics](https://docs.x.com/x-api/fundamentals/metrics) X returns for a post.
3. The star icon: the engagement of the account, the interactions of its
   publications over their impressions. X reports no rate of its own, so it is
   derived from those counters, and it counts the retweets and the quotes as
   interactions like any other.

   ![STATISTICS_ACCOUNT](../static/img/readme/STATISTICS_ACCOUNT.png)

If the X API [rate limit](https://docs.x.com/x-api/fundamentals/rate-limits) is
reached while refreshing the statistics, the last metrics stored on the
account are kept instead of failing.
