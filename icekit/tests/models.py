"""
Test models for ``icekit`` app.
"""
from django.db import models

from fluent_pages.extensions import page_type_pool

from icekit import abstract_models
from icekit.articles.abstract_models import PublishableArticle
from icekit.page_types.layout_page.abstract_models import \
    AbstractUnpublishableLayoutPage
from icekit.plugins import ICEkitFluentContentsPagePlugin


class BaseModel(abstract_models.AbstractBaseModel):
    """
    Concrete base model.
    """
    pass


class FooWithLayout(abstract_models.LayoutFieldMixin):
    pass


class BarWithLayout(abstract_models.LayoutFieldMixin):
    pass


class BazWithLayout(abstract_models.LayoutFieldMixin):
    pass


class ImageTest(models.Model):
    image = models.ImageField(upload_to='testing/')


class Article(PublishableArticle):

    class Meta:
        db_table = 'test_article'


class ArticleWithRelatedPages(PublishableArticle):
    related_pages = models.ManyToManyField('fluent_pages.Page')

    class Meta:
        db_table = 'test_article_with_related'


class UnpublishableLayoutPage(AbstractUnpublishableLayoutPage):
    pass


@page_type_pool.register
class UnpublishableLayoutPagePlugin(ICEkitFluentContentsPagePlugin):
    model = UnpublishableLayoutPage
    render_template = 'icekit/layouts/default.html'
