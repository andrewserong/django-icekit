"""
Admin configuration for ``icekit_events`` app.
"""

# Define `list_display`, `list_filter` and `search_fields` for each model.
# These go a long way to making the admin more usable.

from datetime import timedelta
from dateutil import rrule
import datetime
import json
import logging
import six

from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.template.defaultfilters import slugify
from django.template.response import TemplateResponse
from django.utils.translation import ugettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from icekit.admin import (
    ChildModelFilter, ChildModelPluginPolymorphicParentModelAdmin)
from polymorphic.admin import PolymorphicChildModelAdmin
from timezone import timezone

from . import admin_forms, appsettings, forms, models, plugins

logger = logging.getLogger(__name__)


class EventChildAdmin(PolymorphicChildModelAdmin):
    """
    Abstract admin class for polymorphic child event models.
    """
    base_form = admin_forms.BaseEventForm
    base_model = models.Event
    formfield_overrides = {
        models.RecurrenceRuleField: {'widget': forms.RecurrenceRuleWidget},
    }

    def save_model(self, request, obj, form, change):
        """
        Propagate changes if requested.
        """
        obj.save(propagate=form.cleaned_data['propagate'])


class EventTypeFilter(ChildModelFilter):
    child_model_plugin_class = plugins.EventChildModelPlugin


class EventAdmin(ChildModelPluginPolymorphicParentModelAdmin):
    base_model = models.Event
    list_filter = (
        EventTypeFilter, 'modified')
    list_display = (
        '__str__', 'get_type', 'modified')
    search_fields = ('title', )

    child_model_plugin_class = plugins.EventChildModelPlugin
    child_model_admin = EventChildAdmin

    def get_urls(self):
        """
        Add a calendar URL.
        """
        from django.conf.urls import patterns, url
        urls = super(EventAdmin, self).get_urls()
        my_urls = patterns(
            '',
            url(
                r'^calendar/$',
                self.admin_site.admin_view(self.calendar),
                name='icekit_events_event_calendar'
            ),
        )
        return my_urls + urls

    def calendar(self, request):
        """
        Return event data in JSON format for AJAX requests, or a calendar page
        to be loaded in an iframe.
        """
        if not request.is_ajax():
            context = {
                'is_popup': bool(int(request.GET.get('_popup', 0))),
            }
            return TemplateResponse(
                request, 'admin/icekit_events/event/calendar.html', context)
        tz = timezone.get(request.GET.get('timezone'))
        starts = timezone.localize(
            datetime.datetime.strptime(request.GET['start'], '%Y-%m-%d'), tz)
        ends = timezone.localize(
            datetime.datetime.strptime(request.GET['end'], '%Y-%m-%d'), tz)

        all_events = self.get_queryset(request) \
            .filter(
                Q(all_day=False, starts__gte=starts) |
                Q(all_day=True, date_starts__gte=starts.date())
            ) \
            .filter(
                # Exclusive for datetime, inclusive for date.
                Q(all_day=False, starts__lt=ends) |
                Q(all_day=True, date_starts__lte=ends.date())
            )

        # Get a dict mapping the primary keys for content types to plugins, so
        # we can get the verbose name of the plugin and a consistent colour for
        # each event.
        plugins_for_ctype = {
            plugin.content_type.pk: plugin
            for plugin in plugins.EventChildModelPlugin.get_plugins()
        }
        # TODO: This excludes events for which there is no corresponding plugin
        # (e.g. plugin was enabled, events created, then plugin disabled). This
        # might not be wise, but I'm not sure how else to handle existing
        # events of an unknown type. If ignored here, we probably need a more
        # generic way to ignore them everywhere.
        events = all_events.filter(
            polymorphic_ctype__in=plugins_for_ctype.keys())
        if events.count() != all_events.count():
            ignored_events = all_events.exclude(
                polymorphic_ctype__in=plugins_for_ctype.keys())
            ignored_ctypes = ContentType.objects \
                .filter(pk__in=ignored_events.values('polymorphic_ctype')) \
                .values_list('app_label', 'name')
            logger.warn('%s events of unknown type (%s) are being ignored.' % (
                ignored_events.count(),
                ';'.join(['%s.%s' % ctype for ctype in ignored_ctypes]),
            ))

        data = []
        for event in events.get_real_instances():
            data.append(self.calendar_json(event))
        data = json.dumps(data, cls=DjangoJSONEncoder)
        return HttpResponse(content=data, content_type='applicaton/json')

    def get_type(self, obj):
        return obj.get_real_concrete_instance_class()._meta.verbose_name.title()
    get_type.short_description = "type"

    def calendar_json(self, event):
        """
        Return JSON for a single event
        """
        # Slugify the plugin's verbose name for use as a class name.
        if event.all_day:
            start = event.date_starts
            # `end` is exclusive according to the doc in
            # http://fullcalendar.io/docs/event_data/Event_Object/, so
            # we need to add 1 day to ``date_ends`` to have the end date
            # included in the calendar.
            end = (event.date_ends or event.date_starts) + timedelta(days=1)
        else:
            start = timezone.localize(event.starts)
            end = timezone.localize(event.ends)
        return {
            'title': event.title,
            'allDay': event.all_day,
            'start': start,
            'end': end,
            'url': reverse(
                'admin:icekit_events_event_change', args=[event.pk]),
            'className': self.calendar_classes(event),
        }

    def calendar_classes(self, event):
        """
        Return css classes to be used in admin calendar JSON
        """
        classes = [slugify(event.polymorphic_ctype.name)]

        # quick-and-dirty way to get a color for the type.
        # There are 12 colors defined in the css file
        classes.append("color-%s" % (event.polymorphic_ctype_id % 12))

        # Add a class name for the type of event.
        if event.is_repeat:
            classes.append('is-repeat')
        elif not event.parent:
            classes.append('is-original')
        else:
            classes.append('is-variation')

        # if an event isn't published or does not have show_in_calendar ticked,
        # indicate that it is hidden
        if not event.show_in_calendar:
            classes.append('do-not-show-in-calendar')

        # Prefix class names with "fcc-" (full calendar class).
        classes = ['fcc-%s' % class_ for class_ in classes]

        return classes


admin.site.register(models.Event, EventAdmin)


class RecurrenceRuleAdmin(admin.ModelAdmin):
    formfield_overrides = {
        models.RecurrenceRuleField: {'widget': forms.RecurrenceRuleWidget},
    }
    model = models.RecurrenceRule

    def get_urls(self):
        """
        Add a preview URL.
        """
        from django.conf.urls import patterns, url
        urls = super(RecurrenceRuleAdmin, self).get_urls()
        my_urls = patterns(
            '',
            url(
                r'^preview/$',
                self.admin_site.admin_view(self.preview),
                name='icekit_events_recurrencerule_preview'
            ),
        )
        return my_urls + urls

    @csrf_exempt
    def preview(self, request):
        """
        Return a occurrences in JSON format up until the configured limit.
        """
        recurrence_rule = request.POST.get('recurrence_rule')
        limit = int(request.POST.get('limit', 10))
        try:
            rruleset = rrule.rrulestr(
                recurrence_rule, dtstart=timezone.now(), forceset=True)
        except ValueError as e:
            data = {
                'error': six.text_type(e),
            }
        else:
            data = {
                'occurrences': rruleset[:limit]
            }
        return JsonResponse(data)

admin.site.register(models.RecurrenceRule, RecurrenceRuleAdmin)
