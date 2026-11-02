"""Explicit verified D6B copy; SQLite itself refuses all writes."""
import os
import sqlite3
from django.core.exceptions import ImproperlyConfigured
from .local import *
from apps.organizations.demo.backup import rehearsal_path

try:
    DEMO_REHEARSAL_PATH = rehearsal_path(os.environ.get('AGROCORE_DEMO_REHEARSAL_RUN_ID', ''))
except (ValueError, OSError, KeyError, sqlite3.Error) as error:
    raise ImproperlyConfigured('Verified D6B rehearsal required: ' + str(error)) from None

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3',
                         'NAME': DEMO_REHEARSAL_PATH.as_uri() + '?mode=ro',
                         'OPTIONS': {'uri': True}}}
