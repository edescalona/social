/** @odoo-module **/

import {SocialComment} from "@social_media_sync/components/social_comment/social_comment.esm";
import {patch} from "@web/core/utils/patch";
import {useService} from "@web/core/utils/hooks";

patch(SocialComment.prototype, {
    /** @override */
    setup() {
        super.setup();
        this.socialLinkedinService = useService("social_linkedin_service");
    },
    /**
     * The patch is applied to the prototype, so it answers for every media.
     * Both entry points check the media before acting, or a comment of
     * another connector would be sent to the LinkedIn endpoint.
     *
     * Every comment of the thread is offered, not only the ones the account
     * wrote: the publication belongs to the account, and LinkedIn lets the
     * owner of a publication moderate what is commented on it. Who the
     * deletion acts as is decided server side, so the entry cannot be used
     * to delete on behalf of somebody else.
     *
     * @override
     */
    canDeleteComment() {
        if (this._isLinkedinComment()) {
            return true;
        }
        return super.canDeleteComment();
    },
    /** @override */
    async _onDeleteComment() {
        if (!this._isLinkedinComment()) {
            return super._onDeleteComment();
        }
        return this.socialLinkedinService.deleteLinkedinComment(
            this.props.post.id.raw_value,
            this.props.socialComment.id
        );
    },
    /** @override */
    canLikeComment() {
        if (this._isLinkedinComment()) {
            return true;
        }
        return super.canLikeComment();
    },
    _isLinkedinComment() {
        return this.props.post.media_type.raw_value === "linkedin";
    },
});
