"""Dedicated CLI settings; normal connection remains strictly read-only."""
import os
from django.core.exceptions import ImproperlyConfigured
from .local import *
from apps.organizations.demo.rehearsal_locations import persistent_locations

try:
    DEMO_CONTROLLED_LOCATIONS = persistent_locations(os.environ.get('AGROCORE_DEMO_REHEARSAL_RUN_ID', ''))
except (ValueError, OSError, KeyError) as error:
    raise ImproperlyConfigured('Verified rehearsal location required: ' + str(error)) from None

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3',
    'NAME': DEMO_CONTROLLED_LOCATIONS.copy.as_uri() + '?mode=ro', 'OPTIONS': {'uri': True}}}
