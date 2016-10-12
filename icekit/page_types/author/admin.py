from django.contrib import admin
from fluent_contents.admin import PlaceholderFieldAdmin
from icekit.publishing.admin import PublishingAdmin

from . import models


class AuthorAdmin(PlaceholderFieldAdmin, PublishingAdmin):
    """
    Administration configuration for `Author`.
    """
    change_form_template = 'icekit_authors/admin/change_form.html'
    search_fields = ['slug', 'given_names', 'family_name']
    raw_id_fields = ['portrait', ]
    list_display = PublishingAdmin.list_display + ('given_names', 'family_name')
    prepopulated_fields = {"slug": ("given_names", "family_name")}
    ordering = ("family_name", "given_names",)

admin.site.register(models.Author, AuthorAdmin)
