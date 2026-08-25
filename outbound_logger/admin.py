"""Admin pieces shared by the logs."""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .purge import expired


class ReadOnlyLogAdmin(admin.ModelAdmin):
    """A log records what happened: the admin reads it, nothing edits it."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class RetentionFilter(admin.SimpleListFilter):
    """Selects what the purge would delete, so that the standard delete action can."""

    title = _("retention")
    parameter_name = "expired"
    EXPIRED = "expired"

    def lookups(self, request, model_admin):
        return ((self.EXPIRED, _("Older than the retention window")),)

    def queryset(self, request, queryset):
        if self.value() == self.EXPIRED:
            return expired(queryset)
        return queryset
