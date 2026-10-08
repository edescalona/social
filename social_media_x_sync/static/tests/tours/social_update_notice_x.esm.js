/** @odoo-module */

import {registry} from "@web/core/registry";

/**
 * The *Update* button with an X account that published nothing lately: no
 * figure of the window was refreshed, but the import read its timeline, and
 * that is an update.
 */
registry.category("web_tour.tours").add("social_media_x_sync.update_notice_x", {
    test: true,
    url: "/web#action=social_media_base.social_post_account_action",
    steps: () => [
        {
            content: "The card of the X account is drawn",
            trigger: ".o_content .shadow:contains('X account of the tour')",
            isCheck: true,
        },
        {
            content: "The user asks for an update",
            trigger: "button.o_kanban_statistics_refresh_now",
        },
        {
            content: "And is told that the data was updated",
            trigger:
                ".o_notification .o_notification_content:contains('The data was updated successfully.')",
            isCheck: true,
        },
    ],
});
