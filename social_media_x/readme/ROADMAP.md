- The message of a post is checked against **280 characters**, the limit of an
  account without X Premium. Premium raises it to 25 000, so an account on
  that plan is stopped on a post it could publish perfectly well. That
  subscription is the plan of the X account, and not the plan of the API the
  developer App is enrolled in, which is the one
  `_is_app_without_paid_plan` reads from a rejected call: X answers neither of
  them with the authorized user, and `social.account` stores neither. Once
  Premium can be told apart before publishing, `_get_post_errors` already
  receives the account and the limit becomes per account. Meanwhile the check
  never blocks saving, so the post is still written, and what is refused is
  its publication on X.
