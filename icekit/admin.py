"""
Admin configuration for ``icekit`` app.
"""

# Define `list_display`, `list_filter` and `search_fields` for each model.
# These go a long way to making the admin more usable.
from django.conf import settings
from django.conf.urls import url, patterns
from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.http import JsonResponse
from django.utils.text import capfirst
from django.utils.translation import ugettext_lazy as _
from polymorphic.admin import PolymorphicParentModelAdmin

from icekit.publishing.admin import PublishingAdmin, \
    PublishableFluentContentsAdmin
from icekit.workflow.admin import WorkflowMixinAdmin

from icekit import models


# FILTERS #####################################################################


class ChildModelFilter(admin.SimpleListFilter):
    title = _('type')
    parameter_name = 'type'

    child_model_plugin_class = None

    def lookups(self, request, model_admin):
        lookups = [
            (p.content_type.pk, p.verbose_name.capitalize())
            for p in self.child_model_plugin_class.get_plugins()
        ]
        return lookups

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            content_type = ContentType.objects.get_for_id(value)
            return queryset.filter(polymorphic_ctype=content_type)


# MIXINS ######################################################################


class ICEkitContentsAdmin(PublishingAdmin, WorkflowMixinAdmin):
    """
    A base for generic admins that will include ICEkit features:

     - publishing
     - workflow
    """
    list_display = PublishingAdmin.list_display + \
        WorkflowMixinAdmin.list_display
    list_filter = PublishingAdmin.list_filter + \
        WorkflowMixinAdmin.list_filter


class ICEkitFluentContentsAdmin(
        PublishableFluentContentsAdmin, WorkflowMixinAdmin):
    """
    A base for Fluent Contents admins that will include ICEkit features:

     - publishing
     - workflow
    """
    pass


class PolymorphicAdminUtilsMixin(admin.ModelAdmin):
    """
    Utility methods for working with Polymorphic admins.
    """
    def child_type_name(self, inst):
        """
        e.g. for use in list_display
        :param inst: a polymorphic parent instance
        :return: The name of the polymorphic model
        """
        return capfirst(inst.polymorphic_ctype.name)
    child_type_name.short_description = "Type"


class ChildModelPluginPolymorphicParentModelAdmin(
    PolymorphicParentModelAdmin,
    PolymorphicAdminUtilsMixin
):
    """
    Get child models and choice labels from registered plugins.
    """

    child_model_plugin_class = None
    child_model_admin = None

    def get_child_type_choices(self, request, action):
        """
        Override choice labels with ``verbose_name`` from plugins and sort.
        """
        # Get choices from the super class to check permissions.
        choices = super(ChildModelPluginPolymorphicParentModelAdmin, self) \
            .get_child_type_choices(request, action)
        # Update label with verbose name from plugins.
        plugins = self.child_model_plugin_class.get_plugins()
        if plugins:
            labels = {
                plugin.content_type.pk: capfirst(plugin.verbose_name) for plugin in plugins
            }
            choices = [(ctype, labels[ctype]) for ctype, _ in choices]
            return sorted(choices, lambda a, b: cmp(a[1], b[1]))
        return choices

    def get_child_models(self):
        """
        Get child models from registered plugins. Fallback to the child model
        admin and its base model if no plugins are registered.
        """
        child_models = []
        for plugin in self.child_model_plugin_class.get_plugins():
            child_models.append((plugin.model, plugin.model_admin))
        if not child_models:
            child_models.append((
                self.child_model_admin.base_model,
                self.child_model_admin,
            ))
        return child_models



# MODELS ######################################################################


class LayoutAdmin(admin.ModelAdmin):
    filter_horizontal = ('content_types',)

    def _get_ctypes(self):
        """
        Returns all related objects for this model.
        """
        ctypes = []
        for related_object in self.model._meta.get_all_related_objects():
            model = getattr(related_object, 'related_model', related_object.model)
            ctypes.append(ContentType.objects.get_for_model(model).pk)
            if model.__subclasses__():
                for child in model.__subclasses__():
                    ctypes.append(ContentType.objects.get_for_model(child).pk)
        return ctypes

    def placeholder_data_view(self, request, id):
        """
        Return placeholder data for the given layout's template.
        """
        # See: `fluent_pages.pagetypes.fluentpage.admin.FluentPageAdmin`.
        try:
            layout = models.Layout.objects.get(pk=id)
        except models.Layout.DoesNotExist:
            json = {'success': False, 'error': 'Layout not found'}
            status = 404
        else:
            placeholders = layout.get_placeholder_data()
            status = 200

            placeholders = [p.as_dict() for p in placeholders]

            # inject placeholder help text, if any is set
            for p in placeholders:
                try:
                    p['help_text'] = settings.FLUENT_CONTENTS_PLACEHOLDER_CONFIG.get(p['slot']).get('help_text')
                except AttributeError:
                    p['help_text'] = None

            json = {
                'id': layout.id,
                'title': layout.title,
                'placeholders': placeholders,
            }

        return JsonResponse(json, status=status)

    def get_urls(self):
        """
        Add ``layout_placeholder_data`` URL.
        """
        # See: `fluent_pages.pagetypes.fluentpage.admin.FluentPageAdmin`.
        urls = super(LayoutAdmin, self).get_urls()
        my_urls = patterns(
            '',
            url(
                r'^placeholder_data/(?P<id>\d+)/$',
                self.admin_site.admin_view(self.placeholder_data_view),
                name='layout_placeholder_data',
            )
        )
        return my_urls + urls

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        if db_field.name == "content_types":
            kwargs["queryset"] = ContentType.objects.filter(pk__in=self._get_ctypes())

        return super(LayoutAdmin, self)\
            .formfield_for_manytomany(db_field, request, **kwargs)


class MediaCategoryAdmin(admin.ModelAdmin):
    pass


admin.site.register(models.Layout, LayoutAdmin)
admin.site.register(models.MediaCategory, MediaCategoryAdmin)
