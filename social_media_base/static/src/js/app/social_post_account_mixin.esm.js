/** @odoo-module */
import {SocialImageDialog} from "../../components/social_image_dialog/social_image_dialog.esm";
import {_t} from "@web/core/l10n/translation";
import {useEffect} from "@odoo/owl";

/**
 * The nodes of a card that open the gallery: the counter of the medias the
 * card does not draw, and the images themselves.
 */
const SHOW_ALL_IMAGES_SELECTOR = ".social-all-images, .social-post-images";

export const SocialPostAccountMixin = (T) =>
    class extends T {
        /**
         * Open the gallery from every node of the card that offers it.
         *
         * A kanban card is compiled with a context of its own, where a
         * `t-on-click` cannot reach the methods of the component, so the
         * listener is bound by hand. It is bound on **all** the nodes and not
         * on the first one found: a card with more medias than it draws has
         * two, and binding only the first left the images themselves opening
         * the publication on the social media instead of the gallery.
         *
         * Call it from `setup`: it installs a hook.
         */
        bindShowAllImages() {
            useEffect(
                (...elements) => {
                    const listener = this.onShowAllImages.bind(this);
                    for (const element of elements) {
                        element.addEventListener("click", listener);
                    }
                    return () => {
                        for (const element of elements) {
                            element.removeEventListener("click", listener);
                        }
                    };
                },
                () => [...this.rootRef.el.querySelectorAll(SHOW_ALL_IMAGES_SELECTOR)]
            );
        }

        onShowAllImages(ev) {
            ev.stopPropagation();
            this.dialogService.add(SocialImageDialog, {
                title: _t("All Images"),
                images: JSON.parse(this.record.image_urls.raw_value),
                fullscreen: true,
            });
        }
    };
