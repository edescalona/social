Publishing options are not configurable
---------------------------------------

- The visibility, the feed distribution, the targeting by country, language or
  industry and the third party distribution are fixed in the code, so a
  publication cannot be restricted nor targeted from Odoo. Offering them means
  exposing them on the post and validating the combinations LinkedIn accepts.

  https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api

Size and duration of a video are not checked
--------------------------------------------

- Odoo does not check them before uploading: those limits are the ones of the
  [Videos API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/videos-api)
  and LinkedIn applies them while processing. A video out of limits is
  transferred whole and rejected afterwards, in the processing phase, with
  *LinkedIn could not process the video*.

Rate limits are not handled
---------------------------

- The module does not handle the
  [throttle limits](https://learn.microsoft.com/en-us/linkedin/shared/api-guide/concepts/rate-limits)
  of LinkedIn, applied per day and per application. When LinkedIn answers with
  a limit error, the operation is recorded as failed like any other error and
  has to be retried later by hand; only a credential rejection triggers an
  automatic retry, and only once.
