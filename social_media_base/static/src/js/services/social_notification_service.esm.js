/** @odoo-module **/

import {markup} from "@odoo/owl";
import {registry} from "@web/core/registry";
import {session} from "@web/session";

/** Displays the notifications left in the session by an OAuth callback. */
export const socialNotificationService = {
    dependencies: ["notification"],
    start(env, {notification}) {
        const pending = session.social_media_notification;
        if (!pending || !pending.length) {
            return;
        }
        delete session.social_media_notification;
        for (const notif of pending) {
            if (!notif.message) {
                continue;
            }
            const type = notif.message_type || "danger";
            notification.add(markup(notif.message), {
                type: type,
                sticky: type === "danger",
            });
        }
    },
};

registry
    .category("services")
    .add("social_media_notification", socialNotificationService);
