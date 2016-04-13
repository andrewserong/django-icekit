import json

import django
from django import forms
from django.apps import apps
from django.contrib import messages
from django.contrib.admin import ModelAdmin, SimpleListFilter
from django.conf import settings
from django.conf.urls import patterns, url
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.db.models import F
from django.http import Http404, HttpResponseRedirect, HttpResponse
from django.utils.encoding import force_text
from django.utils.html import escape
from django.utils.translation import ugettext_lazy as _
from django.template import loader, Context


def make_published(modeladmin, request, queryset):
    for row in queryset.all():
        row.publish()
make_published.short_description = _('Publish')


def make_unpublished(modeladmin, request, queryset):
    for row in queryset.all():
        row.unpublish()
make_unpublished.short_description = _('Unpublish')


def http_json_response(data):
    return HttpResponse(json.dumps(data), content_type='application/json')


class PublisherPublishedFilter(SimpleListFilter):
    title = _('Published')
    parameter_name = 'published'

    def lookups(self, request, model_admin):
        return (
            ('1', _('Yes')),
            ('0', _('No'))
        )

    def queryset(self, request, queryset):
        try:
            value = int(self.value())
        except TypeError:
            return queryset

        isnull = not value
        return queryset.filter(publisher_linked__isnull=isnull)


class PublishingStatusFilter(SimpleListFilter):
    """
    Filter events by published status, which will be one of:

        - unpublished: item is not published; it has no published copy
            available via the ``publisher_linked`` relationship.

        - published: item is published but may or may not be up-to-date;
            it has a published copy available via the ``publisher_linked``
            relationship.

        - out_of_date: item is published but the published copy is older
            than the latest draft; the draft's ``publisher_modified_at`` is
            later than this timestamp in the published copy.

        - up_to_date: item is published and the published copy is based
            on the latest draft; the draft's ``publisher_modified_at`` is
            earlier or equal to this timestamp in the published copy.

    Be aware that this queryset filtering happens after the admin queryset is
    already filtered to include only draft copies of published items.
    """
    title = _('publishing status')
    parameter_name = 'publishing_status'

    UNPUBLISHED = 'unpublished'
    PUBLISHED = 'published'
    OUT_OF_DATE = 'out_of_date'
    UP_TO_DATE = 'up_to_date'

    def lookups(self, request, model_admin):
        lookups = (
            (self.UNPUBLISHED, _('Unpublished')),
            (self.PUBLISHED, _('Published')),
            (self.OUT_OF_DATE, _('Published & Out-of-date')),
            (self.UP_TO_DATE, _('Published & Up-to-date')),
        )
        return lookups

    def queryset(self, request, queryset):
        if self.value() == 'unpublished':
            return queryset.filter(publisher_linked__isnull=True)
        elif self.value() == 'published':
            return queryset.filter(publisher_linked__isnull=False)
        elif self.value() == 'out_of_date':
            return queryset.filter(
                publisher_modified_at__gt=F(
                    'publisher_linked__publisher_modified_at'))
        elif self.value() == 'up_to_date':
            return queryset.filter(
                publisher_modified_at__lte=F(
                    'publisher_linked__publisher_modified_at'))


class PublisherAdminForm(forms.ModelForm):
    """
    The admin form that provides functionality for `Publisher`.

    NOTE: Be extremely careful changing the ordering, extending or
    removing classes this class extends. This is because there is a
    super call to `UrlNodeAdminForm` which skips the validation steps
    on `UrlNodeAdminForm`.
    """

    def __init__(self, *args, **kwargs):
        # Add request to self if available. This is to provide site support
        # with `get_current_site` calls.
        self.request = kwargs.pop('request', None)
        super(PublisherAdminForm, self).__init__(*args, **kwargs)

    def clean(self):
        """
        Additional clean data checks for path and keys.

        These are not cleaned in their respective methods e.g.
        `clean_slug` as they depend upon other field data.

        :return: Cleaned data.
        """
        data = super(PublisherAdminForm, self).clean()
        cleaned_data = self.cleaned_data
        instance = self.instance

        # work out which fields are unique_together
        unique_fields_set = instance.get_unique_together()

        if not unique_fields_set:
            return data

        for unique_fields in unique_fields_set:
            unique_filter = {}
            for unique_field in unique_fields:
                field = instance.get_field(unique_field)

                # Get value from the form or the model
                if field.editable:
                    unique_filter[unique_field] = cleaned_data[unique_field]
                else:
                    unique_filter[unique_field] = \
                        getattr(instance, unique_field)

            # try to find if any models already exist in the db; I find all
            # models and then exclude those matching the current model.
            existing_instances = type(instance).objects \
                                               .filter(**unique_filter) \
                                               .exclude(pk=instance.pk)

            if instance.publisher_linked:
                existing_instances = existing_instances.exclude(
                    pk=instance.publisher_linked.pk)

            if existing_instances:
                for unique_field in unique_fields:
                    self._errors[unique_field] = self.error_class(
                        [_('This value must be unique.')])

        return data


class PublisherAdmin(ModelAdmin):
    form = PublisherAdminForm
    # publish or unpublish actions sometime makes the plugins disappear from
    # page so we disable it for now, until we can investigate it further.
    # actions = (make_published, make_unpublished, )
    list_display = ('publisher_object_title', 'publisher_publish',
                    'publisher_status', )
    list_filter = (PublishingStatusFilter, PublisherPublishedFilter)
    url_name_prefix = None

    class Media:
        js = (
            'publisher/publisher.js',
        )
        css = {
            'all': ('publisher/publisher.css', ),
        }

    def __init__(self, model, admin_site):
        super(PublisherAdmin, self).__init__(model, admin_site)

        self.request = None
        self.url_name_prefix = '%(app_label)s_%(module_name)s_' % {
            'app_label': self.model._meta.app_label,
            'module_name': (self.model._meta.model_name
                            if django.VERSION >= (1, 7)
                            else self.model._meta.module_name),
        }

        # Reverse URL strings used in multiple places..
        self.publish_reverse = '%s:%spublish' % (
            self.admin_site.name,
            self.url_name_prefix, )
        self.unpublish_reverse = '%s:%sunpublish' % (
            self.admin_site.name,
            self.url_name_prefix, )
        self.revert_reverse = '%s:%srevert' % (
            self.admin_site.name,
            self.url_name_prefix, )
        self.changelist_reverse = '%s:%schangelist' % (
            self.admin_site.name,
            self.url_name_prefix, )

    def has_publish_permission(self, request, obj=None):
        """
        Determines if the user has permissions to publish.

        :param request: Django request object.
        :param obj: The object to determine if the user has
        permissions to publish.
        :return: Boolean.
        """
        user_obj = request.user
        if user_obj.is_superuser:
            return True
        if not user_obj.is_active:
            return False
        return user_obj.has_perm('%s.can_publish' % self.opts.app_label)

    def publisher_object_title(self, obj):
        return u'%s' % obj
    publisher_object_title.short_description = 'Title'

    def publisher_status(self, obj):
        if not self.has_publish_permission(self.request, obj):
            return ''

        template_name = 'admin/publishing/change_list_publish_status.html'

        publish_btn = None
        if obj.is_dirty:
            publish_btn = reverse(self.publish_reverse, args=(obj.pk, ))

        t = loader.get_template(template_name)
        c = Context({
            'publish_btn': publish_btn,
        })
        return t.render(c)
    publisher_status.short_description = 'Last Changes'
    publisher_status.allow_tags = True

    def publisher_status_column(self, obj):
        """
        Returns `Published`, `Draft` or 'Draft is newer than published` HTML
        rendering depending on the current draft and published version of the
        publishable object.
        """
        is_published_draft = obj.is_draft and obj.has_been_published
        is_up_to_date = not obj.is_dirty

        if is_published_draft:
            if is_up_to_date:
                title = 'Published'
                icon = 'icon-yes.gif'
            else:
                title = 'Draft is newer than published'
                icon = 'icon-unknown.gif'
        else:
            title = 'Draft'
            icon = 'icon-no.gif'

        admin = settings.STATIC_URL + 'admin/img/'
        return (u'<img src="{admin}{icon}" width="10" height="10"'
                u'alt="{title}" title="{title}" />') \
            .format(admin=admin, icon=icon, title=title)
    publisher_status_column.allow_tags = True
    publisher_status_column.short_description = _('Is published')

    def publisher_publish(self, obj):
        template_name = 'admin/publishing/change_list_publish.html'

        is_published = False
        if obj.publisher_linked and obj.is_draft:
            is_published = True

        t = loader.get_template(template_name)
        c = Context({
            'object': obj,
            'is_published': is_published,
            'has_publish_permission':
                self.has_publish_permission(self.request, obj),
            'publish_url': reverse(self.publish_reverse, args=(obj.pk, )),
            'unpublish_url': reverse(self.unpublish_reverse, args=(obj.pk, )),
        })
        return t.render(c)
    publisher_publish.short_description = 'Published'
    publisher_publish.allow_tags = True

    def publishing_admin_filter_for_drafts(self, qs):
        """ Remove published items from the given QS """
        return qs.draft()

    def get_queryset(self, request):
        """
        The queryset to use for the administration list page.

        :param request: Django request object.
        :return: QuerySet.
        """
        # This hack comes from `publisher` and would require significant rework
        # by us to remove it. We can live with it for now.
        self.request = request

        # Obtain the full queryset defined on the registered model.
        qs = self.model.objects

        # Determine if a specific language should be used and filter by it if
        # required.
        try:
            qs_language = self.get_queryset_language(request)
            if qs_language:
                qs = qs.language(qs_language)
        except AttributeError:  # this isn't translatable
            pass

        # Use all draft object versions in the admin.
        qs = self.publishing_admin_filter_for_drafts(qs)

        # If ordering has been specified in the admin definition order by it.
        ordering = getattr(self, 'ordering', None) or ()
        if ordering:
            qs = qs.order_by(*ordering)

        # Return the filtered queryset.
        return qs

    queryset = get_queryset

    def get_urls(self):
        urls = super(PublisherAdmin, self).get_urls()

        publish_name = '%spublish' % (self.url_name_prefix, )
        unpublish_name = '%sunpublish' % (self.url_name_prefix, )
        revert_name = '%srevert' % (self.url_name_prefix, )

        publish_urls = patterns(
            '',
            url(r'^(?P<object_id>\d+)/publish/$',
                self.publish_view, name=publish_name),
            url(r'^(?P<object_id>\d+)/unpublish/$',
                self.unpublish_view, name=unpublish_name),
            url(r'^(?P<object_id>\d+)/revert/$',
                self.revert_view, name=revert_name),
        )

        return publish_urls + urls

    def get_model_object(self, request, object_id):
        # Enforce DB-level locking of the object with `select_for_update` to
        # avoid data consistency issues caused by multiple simultaneous form
        # submission (e.g. by a user who double-clicks form buttons).
        obj = self.model.objects.select_for_update().get(pk=object_id)

        if not self.has_change_permission(request, obj):
            raise PermissionDenied

        if obj is None:
            raise Http404(
                _('%s object with primary key %s does not exist.') % (
                    force_text(self.model._meta.verbose_name),
                    escape(object_id)
                ))

        if not self.has_change_permission(request) \
                and not self.has_add_permission(request):
            raise PermissionDenied

        return obj

    def revert_view(self, request, object_id):
        obj = self.get_model_object(request, object_id)

        if not self.has_publish_permission(request, obj):
            raise PermissionDenied

        obj.revert_to_public()

        if not request.is_ajax():
            messages.success(
                request, _('Draft has been revert to the public version.'))
            return HttpResponseRedirect(reverse(self.changelist_reverse))

        return http_json_response({'success': True})

    def unpublish_view(self, request, object_id):
        obj = self.get_model_object(request, object_id)

        if not self.has_publish_permission(request, obj):
            raise PermissionDenied

        obj.unpublish()

        if not request.is_ajax():
            messages.success(request, _('Published version has been deleted.'))
            return HttpResponseRedirect(reverse(self.changelist_reverse))

        return http_json_response({'success': True})

    def publish_view(self, request, object_id):
        obj = self.get_model_object(request, object_id)

        if not self.has_publish_permission(request, obj):
            raise PermissionDenied

        obj.publish()

        if not request.is_ajax():
            messages.success(request, _('Draft version has been published.'))
            return HttpResponseRedirect(reverse(self.changelist_reverse))

        return http_json_response({'success': True})

    def render_change_form(self, request, context, add=False, change=False,
                           form_url='', obj=None):
        """
        Provides the context and rendering for the admin change form.

        :param request: Django request object.
        :param context: The context dictionary to be passed to the template.
        :param add: Should the add form be rendered? Boolean input.
        :param change: Should the change for be rendered? Boolean input.
        :param form_url: The URL to use for the form submit action.
        :param obj: An object the render change form is for.
        """
        obj = context.get('original', None)
        if obj:
            if not self.has_publish_permission(request, obj):
                context['has_publish_permission'] = False
            else:
                context['has_publish_permission'] = True

                # If the user has publishing permission and if there are
                # changes which are to be published show the publish button
                # with relevant URL.
                publish_btn = None
                if obj.is_dirty:
                    publish_btn = reverse(
                        self.publish_reverse, args=(obj.pk, ))

                # If the user has publishing permission, a draft object and
                # a published object show the unpublish button with relevant
                # URL.
                unpublish_btn = None
                if obj.is_draft and obj.publisher_linked:
                    unpublish_btn = reverse(
                        self.unpublish_reverse, args=(obj.pk, ))

                # By default don't show the preview draft button unless there
                # is a `get_absolute_url` definition on the object.
                preview_draft_btn = None
                if callable(getattr(obj, 'get_absolute_url', None)):
                    preview_draft_btn = True

                # If the user has publishing permission, the object has draft
                # changes and a published version show a revert button to
                # change back to the published information.
                revert_btn = None
                if obj.is_dirty and obj.publisher_linked:
                    revert_btn = reverse(self.revert_reverse, args=(obj.pk, ))

                context.update({
                    'is_dirty': obj.is_dirty,
                    'has_been_published': obj.has_been_published,
                    'publish_btn': publish_btn,
                    'unpublish_btn': unpublish_btn,
                    'preview_draft_btn': preview_draft_btn,
                    'revert_btn': revert_btn,
                })

        context.update({
            'base_change_form_template': self.change_form_template,
        })

        # TODO Why is this hack necessary?
        self._original_change_form_template = self.change_form_template

        # Use change form with fixed side panel.
        # NOTE: Some of the model fields are hidden in the main change form
        # using CSS rules and are duplicated and shown in the side panel
        # instead for better context, e.g. publication related fields are
        # grouped into the 'Save/Publish' tab in the side panel.
        opts = self.model._meta
        app_label = opts.app_label
        self.change_form_template = [
            "admin/%s/%s/publisher_change_form.html" % (
                app_label, opts.model_name),
            "admin/%s/publisher_change_form.html" % app_label,
            "admin/publishing/publisher_change_form.html"
        ]

        response = super(PublisherAdmin, self).render_change_form(
            request, context,
            add=add, change=change, form_url=form_url, obj=obj)

        self.change_form_template = self._original_change_form_template
        return response