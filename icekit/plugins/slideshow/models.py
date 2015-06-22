from django.db import models
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _
from fluent_contents.models import ContentItem, PlaceholderField

from . import appsettings

@python_2_unicode_compatible
class SlideShow(models.Model):
    """
    A reusable Slide Show.
    """
    title = models.CharField(
        max_length=255,
    )
    show_title = models.BooleanField(
        default=False,
        help_text=_('Should the title of the slide show be displayed?')
    )
    content = PlaceholderField(
        'slide_show_content',
        plugins=appsettings.SLIDE_SHOW_CONTENT_PLUGINS,
    )

    def __str__(self):
        return str(self.title)

@python_2_unicode_compatible
class SlideShowItem(ContentItem):
    """
    An slide show from the SlideShow model.
    """
    slide_show = models.ForeignKey(
        'SlideShow',
        help_text=_('A slide show from the slide show library.')
    )

    class Meta:
        verbose_name = _('Reusable slide show')
        verbose_name_plural = _('Reusable slide shows')

    def __str__(self):
        return str(self.slide_show)