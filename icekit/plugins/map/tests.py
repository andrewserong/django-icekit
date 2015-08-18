from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site
from django.contrib.auth import get_user_model
from django.core import exceptions

from django_dynamic_fixture import G
from django_webtest import WebTest
from icekit.models import Layout
from icekit.page_types.layout_page.models import LayoutPage
from icekit.utils import fluent_contents

from . import models

User = get_user_model()


class MapItemTestCase(WebTest):
    def setUp(self):
        self.share_url = 'https://www.google.com.au/maps/place/Chippen+St,' \
            '+Chippendale+NSW+2008/@-33.8877043,151.2005881,17z/data=!4m' \
            '7!1m4!3m3!1s0x6b12b1d86f0291cf:0x74b2d18fb93fed35!2sChippen' \
            '+St,+Chippendale+NSW+2008!3b1!3m1!1s0x6b12b1d86f0291cf:0x74' \
            'b2d18fb93fed35'
        self.layout_1 = G(
            Layout,
            template_name='layout_page/layoutpage/layouts/default.html',
        )
        self.layout_1.content_types.add(
            ContentType.objects.get_for_model(LayoutPage))
        self.layout_1.save()
        self.staff_1 = User.objects.create(
            email='test@test.com',
            is_staff=True,
            is_active=True,
            is_superuser=True,
        )
        self.page_1 = LayoutPage()
        self.page_1.title = 'Test Page'
        self.page_1.slug = 'test-page'
        self.page_1.parent_site = Site.objects.first()
        self.page_1.layout = self.layout_1
        self.page_1.author = self.staff_1
        self.page_1.status = 'p'  # Publish the page
        self.page_1.save()
        self.map_1 = fluent_contents.create_content_instance(
            models.MapItem,
            self.page_1,
            share_url=self.share_url
        )
        self.map_1.parse_share_url()

        self.map_item = models.MapItem(
            parent_type=ContentType.objects.get_for_model(type(self.page_1)),
            parent_id=self.page_1.id,
            placeholder=self.page_1.get_placeholder_by_slot('main')[0],
            share_url=self.share_url,
        )

    def test_regex_finds_values(self):
        response = self.app.get(self.page_1.get_absolute_url())
        response.mustcontain('Chippen+St,+Chippendale')
        response.mustcontain('-33.8877043,151.2005881,17z')

    def test_map_renders(self):
        response = self.app.get(self.page_1.get_absolute_url())
        response.mustcontain('<iframe')

    def test_clean(self):
        self.assertEqual(self.map_item.loc, '0, 0')
        self.assertEqual(self.map_item.place_name, 'Unknown')
        self.map_item.clean()
        self.assertEqual(self.map_item.loc, '-33.8877043,151.2005881,17z')
        self.assertEqual(self.map_item.place_name, 'Chippen+St,+Chippendale+NSW+2008')
        self.map_item.share_url = 'this really should not work'
        with self.assertRaises(exceptions.ValidationError):
            self.map_item.clean()

    def test_str(self):
        self.assertEqual(str(self.map_1), '%s @%s' % (self.map_1.place_name, self.map_1.loc))
        self.map_item.place_name = 'Unknown'
        self.assertEqual(
            str(self.map_item),
            '%s @%s' % (self.map_item.place_name, self.map_item.loc)
        )