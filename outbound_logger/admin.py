"""Admin pieces shared by the logs."""

from django.contrib import admin


class ReadOnlyLogAdmin(admin.ModelAdmin):
    """A log records what happened: the admin reads it, nothing edits it."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
