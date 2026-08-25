from django.apps import AppConfig
from django.core.checks import register
from django.utils.translation import gettext_lazy as _

from ..conf import check_settings


class OutboundHttpConfig(AppConfig):
    """The HTTP log needs requests: pip install django-outbound-logger[http]"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "outbound_logger.http"
    label = "outbound_http"
    verbose_name = _("Outbound HTTP")

    def ready(self):
        register(check_settings)
