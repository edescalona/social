/** @odoo-module **/

import {SocialAccount} from "@social_media_base/components/social_account/social_account.esm";
import {patch} from "@web/core/utils/patch";
import {useBus} from "@web/core/utils/hooks";

/**
 * The card announces what this module imports: the import running in the
 * background, and the publications a check already found and nobody has
 * brought in yet.
 *
 * Base draws neither notice because base imports nothing: an account it just
 * linked is ready to publish and there is nothing to wait for.
 */
patch(SocialAccount.prototype, {
    /** @override */
    setup() {
        super.setup();
        this.state.syncing = false;
        // The flagged accounts themselves and not a boolean, for the same
        // reason base keeps the ones with expired credentials: the notice has
        // to name the account to import.
        this.state.accountsNeedingImport = [];
        useBus(this.env.bus, "SOCIAL:SYNCING", async ({detail: data}) => {
            this.state.syncing = data.syncing;
        });
        useBus(this.env.bus, "SOCIAL:POSTS-NEED-IMPORT", async ({detail: data}) => {
            // The message only speaks of the accounts it names: a user may be
            // responsible for several, and one of them being imported says
            // nothing about the others.
            const named = data.accounts ?? [];
            const kept = this.state.accountsNeedingImport.filter(
                (item) => !named.some((account) => account.id === item.id)
            );
            this.state.accountsNeedingImport = data.needUpdate
                ? kept.concat(named)
                : kept;
        });
    },

    /** @override */
    _updateStateFromAccounts(socialAccounts) {
        super._updateStateFromAccounts(socialAccounts);
        this.state.syncing = socialAccounts.some((item) => item.pending_initial_sync);
        this.state.accountsNeedingImport = socialAccounts
            .filter((item) => item.posts_need_import)
            .map((item) => ({
                id: item.id,
                name: item.name,
                media: item.media_id ? item.media_id[1] : "",
            }));
    },

    /**
     * The accounts with publications to import, as one readable list.
     *
     * The twin of `accountsNeedingUpdateLabel` in base, and it groups them
     * for the same reason: a user responsible for a dozen accounts would
     * otherwise get a dozen notices pushing the dashboard off the screen.
     *
     * @returns {String}
     */
    get accountsNeedingImportLabel() {
        return this.state.accountsNeedingImport
            .map((item) => `[${item.media}] ${item.name}`)
            .join(", ");
    },
});
