import time

from django.core.mail import EmailMultiAlternatives
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from requests.exceptions import RequestException

from outbound_logger.http.session import LoggedSession

from .mail import FLAKY_RECIPIENT

# The flaky endpoint answers 503 the first time each call is made and 200 to the
# retry of that same call, which is the whole point of the page below.
answered_once = set()

# Nothing listens on port 9: the call fails without a response, which is what a
# dead endpoint looks like in the log.
UNREACHABLE_URL = "http://127.0.0.1:9/nothing"

INDEX = """
<h1>django-outbound-logger</h1>
<ul>
  <li><a href="{send}">Send a message</a> - it goes out and is logged as sent.</li>
  <li><a href="{fail}">Send one to a flaky server</a> - it fails, and the admin
      can send it again: the second attempt goes through.</li>
  <li><a href="{fetch}">Call an endpoint</a> - a GET that answers, logged with its response.</li>
  <li><a href="{broken}">Call a dead endpoint</a> - no answer at all, logged as failed.</li>
  <li><a href="{flaky}">Call a flaky endpoint</a> - answers 503, and 200 to the retry.</li>
  <li><a href="{admin}">The mail logs</a> | <a href="{http_admin}">The HTTP logs</a></li>
</ul>
"""


def index(request):
    return HttpResponse(
        INDEX.format(
            send=reverse("send"),
            fail=reverse("send-to-flaky"),
            fetch=reverse("fetch"),
            broken=reverse("fetch-broken"),
            flaky=reverse("fetch-flaky"),
            admin=reverse("admin:outbound_mail_emaillog_changelist"),
            http_admin=reverse("admin:outbound_http_httprequestlog_changelist"),
        )
    )


def send(request):
    build_message("A message that goes out", ["someone@example.com"]).send()
    return redirect("admin:outbound_mail_emaillog_changelist")


def send_to_flaky(request):
    message = build_message("A message the server refuses once", [FLAKY_RECIPIENT])
    message.send(fail_silently=True)
    return redirect("admin:outbound_mail_emaillog_changelist")


def build_message(subject, recipients):
    message = EmailMultiAlternatives(
        subject=subject,
        body="Hello from the example project.",
        to=recipients,
    )
    message.attach_alternative("<p>Hello from the example project.</p>", "text/html")
    message.attach("note.txt", "an attachment, so that the retry has one to carry", "text/plain")
    message.outbound_context = {"sent_from": "the example project"}
    return message


def echo(request):
    """The endpoint the example calls, so that nothing outside is involved."""
    return JsonResponse({"ok": True, "seen": request.GET.dict()})


def fetch(request):
    session = LoggedSession(context={"called_from": "the example project"})
    session.get(request.build_absolute_uri(reverse("echo")), params={"thing": "1"}, timeout=5)
    return redirect("admin:outbound_http_httprequestlog_changelist")


def fetch_broken(request):
    try:
        LoggedSession().get(UNREACHABLE_URL, timeout=2)
    except RequestException:
        pass  # the failed row it leaves behind is the whole point of the page
    return redirect("admin:outbound_http_httprequestlog_changelist")


def echo_flaky(request):
    """Answers 503 to a call it has not seen, 200 to the same call made again."""
    seen = request.GET.get("id", "")
    if seen in answered_once:
        return JsonResponse({"ok": True, "retried": True})

    answered_once.add(seen)
    return JsonResponse({"error": "try again later"}, status=503)


def fetch_flaky(request):
    session = LoggedSession(context={"called_from": "the example project"})
    session.get(
        request.build_absolute_uri(reverse("echo-flaky")),
        params={"id": time.monotonic_ns()},
        timeout=5,
    )
    return redirect("admin:outbound_http_httprequestlog_changelist")
