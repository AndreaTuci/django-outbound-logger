from django.core.mail import EmailMultiAlternatives
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

from .mail import FLAKY_RECIPIENT

INDEX = """
<h1>django-outbound-logger</h1>
<ul>
  <li><a href="{send}">Send a message</a> - it goes out and is logged as sent.</li>
  <li><a href="{fail}">Send one to a flaky server</a> - it fails, and the admin
      can send it again: the second attempt goes through.</li>
  <li><a href="{admin}">The logs in the admin</a></li>
</ul>
"""


def index(request):
    return HttpResponse(
        INDEX.format(
            send=reverse("send"),
            fail=reverse("send-to-flaky"),
            admin=reverse("admin:outbound_mail_emaillog_changelist"),
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
