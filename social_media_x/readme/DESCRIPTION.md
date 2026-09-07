This module provides the necessary functionality for
basic interaction with the X social media.

Main features:
- User account integration.
- Post creation.
- Reports with agnostic metrics, on the account form. The figures they show
  are read back from X by a synchronization module, so without one the card
  of the account stays at zero.
- What X will not publish, shown on the post while it is written. The message
  is checked against **280 characters**, and the medias against **4 images** of
  at most **5 MB** each — **15 MB** for a GIF — in JPG, PNG, WEBP or GIF, and
  **one video** of at most **512 MB** in MP4. X takes images or a video, never
  both in the same post, so a post mixing them is refused instead of warned
  about. The same checks refuse the publication if the post reaches it anyway,
  through an import or an RPC call.

**An X account will never draw a time series in *Social Media* > Statistics.**
That screen reads a history per day, and the
[metrics](https://docs.x.com/x-api/fundamentals/metrics) the API v2 answers
are the current lifetime counters of each post, with no way of asking for them
grouped by day. Giving X a series means either repeating the lifetime counter
on every day, which draws a cumulative curve of a different shape than the
other social media on the same graph, or storing the delta between two
readings, which is false for any day the scheduled action did not run. Neither
is a measurement, so nothing is written: an account of X shows the standard
empty view there, and its figures live on the account form, which is where
they mean something.
