import setuptools

from icekit import __version__

setuptools.setup(
    name='icekit',
    version=__version__,
    packages=setuptools.find_packages(),
    install_requires=[
        'django-bootstrap3',
        'django-fluent-contents',
        'django-fluent-pages',
        'django-model-utils',
        'requests',
        'Pillow',
    ],
    extras_require={
        'brightcove': ['django-brightcove'],
        'dev': [
            'ipdb',
            'ipython',
            'mkdocs',
        ],
        'forms': [
            'django-forms-builder',
        ],
        'search': [
            'django-haystack',
            'django-fluent-pages[flatpage,fluentpage]',
        ],
        'test': [
            'coverage',
            'django-dynamic-fixture',
            'django-nose',
            'django-webtest',
            'mock',
            'nose-progressive',
            'WebTest',
        ],
    },
)
