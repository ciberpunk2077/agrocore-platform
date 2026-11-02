"""D7A viewer only. No seed/write capabilities and no normal settings changes."""
from django.core.exceptions import ImproperlyConfigured
from .local import *
from apps.organizations.demo.demo_view import verified_locations

try:
    DEMO_VIEW_LOCATIONS = verified_locations()
except Exception:
    raise ImproperlyConfigured('The certified D7A demo files are unavailable or changed.') from None

DEBUG = False
ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3',
    'NAME': DEMO_VIEW_LOCATIONS.copy.as_uri() + '?mode=ro', 'OPTIONS': {'uri': True}}}
DATABASE_ROUTERS = []
EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
