This module is installed on its own as soon as *Social Media Sync* and *Social
Media Linkedin* are both present, which is what a bridge module is for: the
choice to synchronize was already made by whoever installed *Social Media
Sync*, and this only keeps a LinkedIn page from being left without the half
that belongs to it.

Installing *Social Media Linkedin* alone is a valid installation: the account
is linked, publishes, deletes and shows the daily figures of its page.

Upgrading from a version where *Social Media Linkedin* held both halves
---------------

The stored field `social.account.linkedin_statistics_checkpoint` moves from
*Social Media Linkedin* to this module, and no migration script ships with
it. Recreate the database instead of updating it in place.

Updating in place is what loses the column, and losing it has a visible
consequence: the checkpoint is the baseline the update check compares
against, so the first pass of the bihourly cron after the deployment finds no
baseline on any account and turns the *Update* badge on for all of them at
once.
