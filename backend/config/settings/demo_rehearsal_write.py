"""Reserved configuration. D6C-1 cannot activate persistent writes."""
from django.core.exceptions import ImproperlyConfigured

raise ImproperlyConfigured('D6C-1: persistent rehearsal writes are disabled; independent D6C-2 authorization is required.')
