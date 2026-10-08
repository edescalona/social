/** @odoo-module **/

import {SocialKanbanController} from "@social_media_base/js/views/kanban/social_kanban_controller.esm";
import {_t} from "@web/core/l10n/translation";
import {patch} from "@web/core/utils/patch";

patch(SocialKanbanController.prototype, {
    /**
     * An X timeline read by the import is an update too.
     *
     * The figures are refreshed before the import, over the publications of
     * the window, so an X account with nothing published lately answers that
     * nothing was refreshed even when *Update* has just read its timeline.
     * This bridge reads the timeline of every X account on each *Update*,
     * because X cannot say beforehand whether there is anything new
     * (`_detects_pending_posts` is false): an X account on the dashboard and
     * an import that answered mean X was read.
     *
     * When the rate limit window of X keeps the timeline from being read, X
     * warns with an `info` notification, which leaves `social_error` unset,
     * so this one can still appear below it.
     *
     * @override
     */
    _updateStatisticsMessage(refreshed) {
        if (
            !refreshed &&
            this.model.postsImported &&
            this.socialState.accounts.some((account) => account.media_type === "x")
        ) {
            return _t("The data was updated successfully.");
        }
        return super._updateStatisticsMessage(refreshed);
    },
});
