# Copyright 2026 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

# How many replies one page of the conversation asks for. A hundred is the
# ceiling of the recent search endpoint, and asking for it is free: the same
# request that answers ten answers a hundred. Without it X applies its own
# default of ten, and a thread of eleven replies is read wrong.
_SEARCH_MAX_RESULTS_X = 100

# How many pages of one conversation are walked. Five hundred replies is
# already an extraordinary thread, and the ceiling is what keeps a single
# dialog from spending the quota of the whole database: the dialog refreshes
# itself every two minutes while it stays open, so what is paid here is paid
# again every two minutes.
_COMMENTS_MAX_PAGES_X = 5
