"""Dedicated disposable file database for D2 tests; never for local execution."""
import atexit
from pathlib import Path
import tempfile

from .base import *  # noqa: F403

DEMO_D2_TEST_ROOT = Path(tempfile.mkdtemp(prefix='agrocore-d2-')).resolve()
DATABASES = {'default': {
    'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:',
    'TEST': {'NAME': str(DEMO_D2_TEST_ROOT / 'disposable.sqlite3')},
}}


def _remove_empty_test_root():
    try:
        DEMO_D2_TEST_ROOT.rmdir()
    except OSError:
        pass  # Never recursively remove an unexpected file or directory.


atexit.register(_remove_empty_test_root)
