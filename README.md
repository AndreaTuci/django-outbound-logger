# django-outbound-logger

[![PyPI version](https://img.shields.io/pypi/v/django-outbound-logger.svg)](https://pypi.org/project/django-outbound-logger/)
[![Python versions](https://img.shields.io/pypi/pyversions/django-outbound-logger.svg)](https://pypi.org/project/django-outbound-logger/)
[![License: MIT](https://img.shields.io/pypi/l/django-outbound-logger.svg)](https://github.com/AndreaTuci/django-outbound-logger/blob/main/LICENSE)

Every email your project sends, and every HTTP request it makes, written to the
database with the outcome of the send — and sent again when it failed.

When a customer says "I never got that email", the answer is a row: who it went
to, what it said, whether the server took it, and the traceback if it did not.
Same for the call to the CRM that nobody noticed had been failing for a week.

## Install

```bash
pip install django-outbound-logger          # the mail log
pip install django-outbound-logger[http]    # and the HTTP one, which needs requests
```

Django 4.2 or later, Python 3.10 or later.

## Logging the mail

```python
INSTALLED_APPS = [..., "outbound_logger.mail"]

EMAIL_BACKEND = "outbound_logger.mail.backends.LoggingEmailBackend"
OUTBOUND_LOGGER = {
    "MAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",  # the one that really sends
}
```

```bash
python manage.py migrate
```

That is all. The logging backend writes the row and hands the message to the
backend you named — SMTP, console, an ESP backend such as Anymail, anything —
so nothing else in your project changes.

Each row holds the envelope (from, to, cc, bcc, reply-to), the subject, the text
and HTML bodies, the headers, what the attachments were, the raw MIME message,
and the outcome. Every send leaves an attempt behind, with its traceback when it
failed, so the history is not overwritten by the next try.

A message is logged **before** the connection is opened: a mail server that is
down leaves rows behind, not a hole.

### On Django 6.1 and later, with MAILERS

```python
MAILERS = {
    "default": {"BACKEND": "outbound_logger.mail.backends.LoggingEmailBackend"},
    "smtp": {"BACKEND": "django.core.mail.backends.smtp.EmailBackend", "OPTIONS": {...}},
}
OUTBOUND_LOGGER = {"MAIL_MAILER": "smtp"}
```

Use `MAIL_MAILER` (the alias of another mailer) instead of `MAIL_BACKEND` (a
dotted path). Setting both is refused.

## Sending a failed message again

From the admin, with the action *Send the selected messages again* — which asks
for the `outbound_mail.retry_emaillog` permission, so that a read-only viewer
cannot make mail go out. From the command line:

```bash
python manage.py retry_failed_emails --dry-run
python manage.py retry_failed_emails --since 7 --max-attempts 3
```

From your own code:

```python
from outbound_logger.mail.retry import retry_emails

report = retry_emails(EmailLog.objects.filter(status="failed"))
report.succeeded, report.failed, report.skipped   # skipped carries the reason
```

The message is rebuilt from the fields, with the attachments lifted back out of
the stored MIME, and sent on the same row: the `Message-ID` stays the one the
first attempt carried. Nothing is raised — a message that cannot be rebuilt is
skipped with its reason (already sent, body not stored, attachments not stored).

## Logging the HTTP requests

```python
INSTALLED_APPS = [..., "outbound_logger.http"]
```

```python
from outbound_logger.http.session import LoggedSession

session = LoggedSession(context={"integration": "crm"})
response = session.post("https://crm.example.com/contacts", json=payload)
```

`LoggedSession` is a `requests.Session`, so everything you know still applies.
What is logged is what was really sent: the final url, the headers after the
session and the authentication have had their say, the encoded body. Failures
are logged and raised again — what to do with them stays your call.

Sensitive headers never reach the database: `Authorization`, `Cookie`,
`Set-Cookie` and friends are replaced with `[redacted]` before the row is
written. The list is yours to change with `HTTP_REDACT_HEADERS`. Credentials
written into the url itself go the same way. Secrets passed as query parameters
do not: their names differ from one API to the next, and guessing would hide the
wrong things.

A response asked for with `stream=True` is left unread, so the stream is still
yours to consume.

## Sending a failed request again

Only requests marked as retriable are ever sent again. By default those are the
idempotent methods — GET, HEAD, PUT, DELETE, OPTIONS, TRACE — because repeating
a POST creates a second order. Say otherwise per call or per session:

```python
session.post(url, json=payload, retriable=True)     # an upsert, or an idempotency key
LoggedSession(retriable=False)                      # nothing from this session
```

Since the credentials were redacted, a replay needs a session that still has
them. Point the setting at a callable of yours:

```python
# settings.py
OUTBOUND_LOGGER = {"HTTP_SESSION_FACTORY": "myproject.crm.build_session"}

# myproject/crm.py
def build_session():
    session = requests.Session()
    session.auth = (USER, PASSWORD)
    return session
```

The request is prepared *on* that session, so it puts its own authentication
back. Then, from the admin action *Send the selected requests again* (it asks
for the `outbound_http.retry_httprequestlog` permission), or:

```bash
python manage.py retry_failed_requests --include-server-errors --dry-run
```

A retry counts as succeeded when the endpoint answered below 500: a 502 is the
failure you were retrying, a 404 is an answer.

## Tying a log to your own data

Neither log knows about your models, and neither will grow a foreign key into
them. They carry a free JSON field instead:

```python
message = EmailMultiAlternatives(...)
message.outbound_context = {"contact_id": contact.pk}
message.send()

# or, when you only have django.core.mail.send_mail():
send_mail(..., headers={"X-Outbound-Context": '{"contact_id": 12}'})

session.get(url, context={"contact_id": contact.pk})
```

The header is removed before the message goes out: it is ours, the recipient has
no business seeing it.

## Keeping the tables in check

Nothing is ever deleted on its own. When you want it deleted, from a scheduled
task of yours:

```python
from outbound_logger.mail.purge import purge_email_logs
from outbound_logger.http.purge import purge_http_logs

purge_email_logs()                     # older than RETENTION_DAYS
purge_http_logs(older_than_days=30)
```

from cron:

```bash
python manage.py purge_email_logs --days 90
python manage.py purge_http_logs --dry-run
```

or from the admin: filter by *Retention → Older than the retention window*,
select all, and use Django's own delete action.

## Keeping the log out of your transactions

A log is written on the connection the caller is using. If that caller is inside
a `transaction.atomic()` block that later rolls back, the message has gone out
but its row goes away with everything else — the one case where the log lies.

Give the logs a connection of their own and they stop caring what the caller
does:

```python
DATABASES = {
    "default": {...},
    "logs": {...},          # the same database is fine: what matters is the second connection
}
DATABASE_ROUTERS = ["outbound_logger.routers.OutboundLoggerRouter"]
OUTBOUND_LOGGER = {"DATABASE": "logs"}
```

```bash
python manage.py migrate --database=logs
```

The router keeps the two log tables on that alias and every other table off it.
Neither log has a foreign key into your models, so nothing is torn in half by
the split. Setting the alias without adding the router is reported by
`manage.py check` rather than silently doing nothing.

## Settings

Everything lives in one dict. A key that is not on this list is reported by
`manage.py check` rather than ignored.

| Setting | Default | What it does |
| --- | --- | --- |
| `MAIL_BACKEND` | `django...smtp.EmailBackend` | The backend that really sends. |
| `MAIL_BACKEND_OPTIONS` | `{}` | Keyword arguments for it. |
| `MAIL_MAILER` | `None` | A `MAILERS` alias to delegate to instead (Django 6.1+). |
| `STORE_BODY` | `True` | Store bodies at all, or only the metadata. |
| `MAX_BODY_BYTES` | `5242880` | Above this, the MIME and the request body are dropped and the response body is cut. |
| `RETENTION_DAYS` | `90` | How old a log has to be for the purge to take it. |
| `HTTP_REDACT_HEADERS` | `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`, `X-Api-Key`, `X-Auth-Token` | Header values replaced before storing. |
| `HTTP_SESSION_FACTORY` | `None` | Dotted path to a callable returning the session a replay is prepared on. |
| `HTTP_RETRY_TIMEOUT` | `30` | Seconds a replayed request waits. |
| `DATABASE` | `None` | Alias the logs live on, with the router in `DATABASE_ROUTERS`. |

## Two things worth knowing

**"Sent" means the backend took it**, not that anybody received it. Bounces
happen after that and this package never sees them.

**The logger never stops the send.** If a message cannot be recorded — a
malformed header, the log database down — the failure goes to the `outbound_logger`
Python logger and the message is handed to the backend anyway. An audit trail is
not worth losing mail over.

**In your project's own tests nothing is logged.** Django's test runner replaces
`EMAIL_BACKEND` with the locmem backend, which is what you want: your test suite
should not be filling a table. Point it back at the logging backend with
`@override_settings` in the few tests that are about the logging itself.

## Translations and types

The admin labels and messages are translated into Italian; every string is
marked, so another language is a catalogue away.

The package is annotated but does not ship `py.typed` yet. A type checker cannot
see a `TextChoices` member whose label is a lazy translation as anything but a
tuple, so claiming the package checks clean would not be true.

## The example project

`example/` is a small Django project to try all of it by hand: a message that
goes out, one refused by a flaky server, a call that answers, one to a dead
endpoint, and one that answers 503 and then 200 to the retry.

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Running the tests

```bash
python runtests.py
```

No test dependencies beyond Django. The suite runs on Django 4.2, 5.2 and 6.1.

## License

MIT.
