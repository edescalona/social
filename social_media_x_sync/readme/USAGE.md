Importing the publications
------------------------

- The timeline of the account is read with
  [the posts of a user](https://docs.x.com/x-api/posts/user-posts-timeline),
  which answers up to **100 publications in a single request** and is not
  paginated: what is older than those hundred is not imported, in order to
  spare the requests of the plan. Retweets and replies are excluded, so only
  the original publications of the account are stored.
- Each media of an imported publication is downloaded once and stored as an
  attachment. A media already stored is not asked for again.
- The *Update* button of the dashboard card runs the same import on demand.
- With *Enable since* the import only asks for what was published after the
  stored publication, so the older publications are no longer read by this
  import. The ones published in the last 30 days are refreshed all the same by
  *Social Media X*, which reads their figures by identifier. The card of the
  account is unaffected either way: the figures are written on each
  publication, and the card adds up every publication stored.

Comments
------------------------

- The comments of a publication are read with the
  [recent search](https://docs.x.com/x-api/posts/recent-search) endpoint of X,
  which only covers the **last 7 days**: the replies to older publications are
  not shown on the dashboard even though the post has them. Retweets and
  quotes are excluded as well, only the replies are listed.
- The conversation is read a hundred replies at a time, following the token X
  answers with until it runs out or five pages have been read. Read to the
  end, how many replies each comment has is counted in Odoo and never asked to
  X again; cut short by that ceiling or by the limit of requests of the plan,
  no number is stated, and the dashboard offers to unfold the replies of every
  comment.
- Answering a publication and answering one of its comments are the same call
  to X: on X a comment is a post like any other, and what changes is the post
  being replied to.

Verification of a publication
------------------------

- Before acting on a publication from the dashboard, Odoo checks on X that the
  post still exists. If it was deleted directly on X, the action stops, the
  publication is marked as *Deleted* in Odoo and the notice *The post does not
  exist or has been deleted.* is shown.
- Only the *Not Found* answer of X marks the publication as deleted. A
  throttled application, or any other failure, means the post could not be
  read and the publication is left untouched.

Rate limits
------------------------

The endpoints this module spends from the plan of the account are the timeline
of the user, the recent search of the comments, the publication of a reply and
the read of a single post. Each of them has its own window on the account, the
same record where *Social Media X* stores the ones it spends, and when X
answers that one is exhausted Odoo stops calling that endpoint until the
window expires.

While the window of the comments lasts, opening the conversation of a
publication shows the notice *The comments could not be read from X. The
account may have reached the limit of requests of its plan.* instead of an
empty thread, and a refresh in that state leaves the comments already on
screen untouched.

While the window of the replies lasts, publishing a comment answers *The
comment could not be published on X. The account may have reached the limit of
requests of its plan.* and the text stays in the composer, instead of
reporting a reply X never received.

Uninstalling
------------------------

Uninstalling this module leaves the account linked and able to publish. What
goes with it is the checkpoint of the import: *Enable since*, *Post since* and
the reference of the last publication read.
