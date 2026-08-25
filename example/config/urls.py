from django.contrib import admin
from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("send/", views.send, name="send"),
    path("send/flaky/", views.send_to_flaky, name="send-to-flaky"),
    path("admin/", admin.site.urls),
]
