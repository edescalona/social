Importing what an account already published.
---------------

- Right after an account is linked, its publications and their statistics are
  imported: the scheduled action *Social: Initial sync of the new accounts* is
  triggered on the spot and the dashboard shows the account as syncing until
  it is over.
- If that first import fails, the account stops waiting for it and is **not**
  retried on its own: press the *Update* button of the dashboard to import it
  again. The reason is left in the chatter of the account, because the
  scheduled action runs with nobody connected to be notified.
- If the import loses a race against another update of the same account, it
  keeps the account waiting and asks the scheduled action to come back a few
  minutes later. Unlike a web request, a scheduled action gets no retry of its
  own.
- If the social media does not let the import run —the requests of the plan
  are spent, and the account gets a notice saying so— nothing is brought in
  and nothing is recorded as a failure: the account keeps waiting and the
  scheduled action is asked to come back a few minutes later. The *Update*
  button of the dashboard behaves the same way, and only stops announcing the
  first import once the social media was really read.
- Publications created outside of Odoo are the only ones whose medias the
  import has to download, and so the only ones whose images appear on the
  dashboard after it rather than before: a publication sent from Odoo already
  shares the medias of its post.
- The first import fills the time series of the account backwards, as far back
  as the social media answers by day. How far that is belongs to the social
  media, not to Odoo, so two accounts may well start with a different depth of
  history.
- Afterwards, the *Update* button of the dashboard imports again on demand.
  Without this module that button only refreshes the daily series; with it, it
  does both.
- The figures imported for a publication — impressions, social media clicks,
  shares, likes, comments, interactions and engagement — are added by this
  module to the list of publications, to their form and to the *Statistics*
  dialog of a card. Without it those views show only the tracked clicks, which
  are counted by the link tracker of *Social Media Base*.

Noticing what was deleted on the social media.
---------------

- The ordinary import asks the social media only about what it needs, which is
  what keeps it affordable on an account with thousands of publications. What
  it cannot notice that way is that a publication was **deleted** on the social
  media: nothing is left to ask about.
- The scheduled action *Social: Full resync of the accounts* reads everything
  again once a week and reconciles it, and each connector may also offer to run
  it on demand from the account form. A publication deleted on the social media
  may therefore take up to a week to be reported as such.
- A publication found gone is marked as *Deleted* and keeps its reference on
  the social media: detection is not infallible, so a line wrongly marked can
  be recognised and restored by the next full pass.
- Opening a publication, from its form or from its card on the dashboard, asks
  the social media first. A publication deleted there is reported as *The post
  does not exist or has been deleted.* and marked right away, instead of
  waiting for the weekly pass. A check that fails to reach the social media
  answers *not deleted*: a publication is not gone just because Odoo could not
  read it.

Comments and reactions.
---------------

- Commenting a publication from the dashboard publishes the comment on the
  social media, under the account of the publication, which is what the
  composer announces.
- Answering a comment moves the composer under it, so the reply is written
  where it will be read, and it stays there afterwards for the next one.
  Pressing the entry again hands the composer back to the head of the dialog,
  which also holds it while the answered comment is not on the list.
- A comment is answered where the social media serves the replies. Where the
  whole thread already arrives with the comments, the replies are nested from
  what is already on screen and nothing else is asked for.
- *Recommend* is offered both on the publication and on each of its comments,
  and is sent under the same account. It is only shown where the social media
  supports it on comments: a connector that recommends them declares itself,
  and the entry is not rendered for the publications of the ones that do not.
- The entry is a toggle: a social media holds one reaction per account, so it
  draws what the account already recommended and pressing it there withdraws
  the reaction. A social media that could not be read leaves the entry as it
  was drawn instead of claiming one thing or the other.
- A reaction or a comment that fails with a *not found* does not mark the
  publication as deleted on its own: the publication is asked about first,
  because a social media answers the same for a reference it does not
  recognise and for a lost permission.
