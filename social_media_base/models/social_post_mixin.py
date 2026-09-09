# Copyright 2026 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from odoo import api, fields, models

# Sort key of a media that has no database identifier yet, so that it is
# ordered after the stored ones instead of being compared with them.
UNSAVED_MEDIA_ORDER = float("inf")


class SocialPostMixin(models.AbstractModel):
    """What a post and its publications draw and publish in the same order.

    ``social.post`` is the content the user writes once and
    ``social.post.account`` is that same content as it exists on one social
    media. Both carry the images of the post, and both have to show them the
    way the user arranged them, so what is previewed before publishing and
    what is published are never two different galleries. This mixin is where
    that shared handling of the medias lives::

        class SocialPost(models.Model):
            _name = "social.post"
            _inherit = ["social.post.mixin"]

    It solves two problems the inheriting models would otherwise solve twice:

    * **Order.** ``ir.attachment`` is ordered by ``id desc``, so a record
      re-read from database returns its images newest first.
      :meth:`_sorted_medias` puts them back in the order they were added, and
      everything that draws or uploads them goes through it.
    * **Caching.** :meth:`_compute_image_urls` embeds the checksum of the
      attachment in its URL, so the browser caches the image as immutable
      instead of revalidating it on every render, and a modified image still
      gets a new URL. On a dashboard of dozens of posts this is the difference
      between a hundred conditional requests and none.

    The models inheriting it declare ``image_ids`` and ``video_ids``
    themselves, which is why the ``@api.depends`` of ``image_urls`` and
    ``video_urls`` are written as lambdas.
    """

    _name = "social.post.mixin"
    _description = "Media Attached to Posts and Publications"

    image_urls = fields.Char(compute="_compute_image_urls", store=True)
    video_urls = fields.Char(
        compute="_compute_video_urls",
        store=True,
        help="URL of each video of this record, in the order they were added.",
    )

    def _media_attachments_to_skip(self):
        """Return the medias this record must not claim as its own.

        Empty here: a post owns every media it carries. A publication
        overrides it with the ones it shares with its post.

        :rtype: recordset of ``ir.attachment``
        """
        return self.env["ir.attachment"]

    def _anchor_media_attachments(self):
        """Attach the medias of these records to them.

        The upload widget stores them while the record has no id yet, and the
        import creates them together with the publication, so they end up
        with an empty ``res_id``: in that state only the administrators can
        read them and everybody else gets a placeholder instead of the image.

        What the record does not own is left alone, which is what
        :meth:`~._media_attachments_to_skip` answers.
        """
        for record in self:
            shared = record._media_attachments_to_skip()
            attachments = (record.image_ids | record.video_ids).filtered(
                lambda attachment, shared=shared: not attachment.res_id
                and attachment not in shared
            )
            if attachments:
                attachments.sudo().write(
                    {"res_model": record._name, "res_id": record.id}
                )

    @staticmethod
    def _sorted_medias(attachments):
        """Return the attachments in the order the user added them.

        ``ir.attachment`` is ordered by ``id desc`` and a many2many is read
        with the order of its comodel, so a record re-read from database
        returns the attachments newest first. Everything that publishes or
        draws them goes through here, so what is previewed and what is
        published never disagree.

        A record that is not stored yet carries a ``NewId``, which cannot be
        compared with anything: those keep the order they were added in and
        stay last, which is where the user just put them. This happens on
        every onchange, before the post is saved.

        :param attachments: the ``ir.attachment`` recordset to order.
        :rtype: odoo.models.Model
        """
        return attachments.sorted(
            lambda attachment: attachment._origin.id or UNSAVED_MEDIA_ORDER
        )

    @api.depends(lambda self: ["image_ids", "image_ids.checksum"])
    def _compute_image_urls(self):
        """Build the image URLs of the post.

        The attachment checksum is embedded in the URL so that Odoo serves the
        image as immutable and the browser caches it instead of revalidating it
        on every page load. A new checksum yields a new URL, so an updated
        image is fetched again without any cache busting on the client side.

        The dependency is a lambda because ``image_ids`` is declared by the
        models inheriting this mixin, not by the mixin itself.

        The images are ordered by :meth:`_sorted_medias`: without it the
        gallery would draw them newest first, in another order than the one
        they are published in.
        """
        for post in self:
            post.image_urls = json.dumps(
                [
                    f"/web/image/{image.id}-{image.checksum}"
                    if image.checksum
                    else f"/web/image/{image.id}"
                    for image in self._sorted_medias(post.image_ids)
                ]
            )

    @api.depends(lambda self: ["video_ids", "video_ids.checksum"])
    def _compute_video_urls(self):
        """Build the video URLs of the post.

        The checksum makes Odoo serve the file as immutable and the browser
        cache it, exactly as it does for the images, and a replaced video
        yields a new URL on its own.

        The route is not the one of the images: ``/web/content`` has no
        ``<id>-<unique>`` variant, so the checksum travels in the query
        instead, and a video asked to ``/web/image`` would come back as the
        placeholder of a file that is not an image.

        The dependency is a lambda because ``video_ids`` is declared by the
        models inheriting this mixin, not by the mixin itself.

        The videos are ordered by :meth:`_sorted_medias`, so a record draws
        them in the order they were added.
        """
        for post in self:
            post.video_urls = json.dumps(
                [
                    f"/web/content/{video.id}?unique={video.checksum}"
                    if video.checksum
                    else f"/web/content/{video.id}"
                    for video in self._sorted_medias(post.video_ids)
                ]
            )
