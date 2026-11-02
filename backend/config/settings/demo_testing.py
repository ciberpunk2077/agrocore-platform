"""D1 tests only. Fixtures are disposable SQLite files, never db.sqlite3."""
from .base import *  # noqa: F403

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
