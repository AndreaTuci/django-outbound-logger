# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project follows [semantic versioning](https://semver.org/).

## [0.3.0] - 2026-08-26

An adversarial review of 0.2.0. Nothing here changes how the package is set up,
but run `manage.py migrate` for the new permissions and indexes, and grant
`retry_emaillog` / `retry_httprequestlog` to whoever used to retry from the admin.

### Fixed

- A send with `fail_silently=True` raised `ImproperlyConfigured` on Django 6.1
  whenever `MAILERS` and `MAIL_MAILER` were in use: Django's own private
  keywords were mistaken for connection options meant for the delegate.
- A message that could not be logged aborted the whole batch, so messages Django
  would have sent never went out. The failure is now logged and the message is
  sent anyway.
- An attachment given as an `email.message.MIMEPart` — the way Django 6.1 asks
  for one — crashed the capture.
- A connection failing to close no longer sinks a send that worked.
- An HTTP failure raised before the request was prepared was marked retriable,
  and the replay would have sent it stripped of its body.
- A replayed POST no longer follows redirects: the 200 of the redirect target
  would have hidden the failure being retried.
- Values longer than their column, and NUL bytes, no longer reach the database.
- A session-wide `stream = True` is honoured; a bytes header is stored as text
  rather than as its repr.
- `--max-attempts 0` and `--since 0` mean zero, not "no limit".
- The purge deletes in batches instead of loading every expired row at once, and
  both logs gained the index it filters on.
- The changelist no longer loads the stored MIME and bodies to draw a table that
  does not show them.
- Alternatives other than HTML — a calendar invitation, say — survive a retry.
- The purge command prints the cutoff in the project's timezone.

### Added

- `retry_emaillog` and `retry_httprequestlog` permissions: the admin retry
  actions ask for them, so a read-only viewer can no longer make things go out.
- Credentials written into a request url are redacted like the headers.
- `OUTBOUND_LOGGER["DATABASE"]` set to `"default"` is now refused by a system
  check: the router would have kept every other app off the only database.

### Changed

- A malformed `X-Outbound-Context` header no longer raises: the message goes out
  and the error is reported through Python logging.

## [0.2.0] - 2026-08-26

### Added

- `OUTBOUND_LOGGER["DATABASE"]` and `outbound_logger.routers.OutboundLoggerRouter`:
  the logs can live on a database connection of their own, so a rollback in the
  caller's transaction no longer erases the log of a message that really went
  out. `manage.py check` reports the alias without the router.
- Italian translation of the admin labels and messages.
- Type annotations across the package. The distribution does not ship `py.typed`
  yet: see the note in the readme.

### Fixed

- Two strings were invisible to `makemessages` because they sat inside f-strings.

## [0.1.0] - 2026-08-25

First release.

### Added

- `outbound_logger.mail`: an email backend that logs every message — envelope,
  bodies, headers, attachment metadata, raw MIME — with the outcome of the send
  and one row per attempt, then hands the message to the backend that really
  sends. Works with `EMAIL_BACKEND` and with `MAILERS` on Django 6.1.
- Sending a failed message again, from the admin, from `retry_failed_emails` or
  from `retry_emails()`. The message is rebuilt from the fields, with the
  attachments lifted back out of the stored MIME, on the same row.
- `outbound_logger.http`: `LoggedSession`, a `requests.Session` that logs every
  call with what was really sent, the response, and how long it took. Sensitive
  headers are redacted before the row is written.
- Sending a failed request again, from the admin, from `retry_failed_requests`
  or from `retry_requests()`. Only requests marked retriable are ever repeated,
  and the replay is prepared on the project's own session so that the
  credentials the log does not hold come back.
- Retention: `purge_email_logs()`, `purge_http_logs()`, a management command for
  each, and an admin filter that feeds Django's own delete action.
- Read-only admin for both logs, with the attempts alongside.
- `manage.py check` reports a misspelled or contradictory setting.

[0.3.0]: https://github.com/AndreaTuci/django-outbound-logger/releases/tag/v0.3.0
[0.2.0]: https://github.com/AndreaTuci/django-outbound-logger/releases/tag/v0.2.0
[0.1.0]: https://github.com/AndreaTuci/django-outbound-logger/releases/tag/v0.1.0
