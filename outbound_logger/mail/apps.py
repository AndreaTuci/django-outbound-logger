from django.apps import AppConfig
from django.core.checks import register
from django.utils.translation import gettext_lazy as _

from ..conf import check_settings


class OutboundMailConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "outbound_logger.mail"
    label = "outbound_mail"
    verbose_name = _("Outbound mail")

    def ready(self) -> None:
        register(check_settings)
