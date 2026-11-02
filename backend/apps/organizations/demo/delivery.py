"""Authenticated encrypted delivery for disposable D2 tests only."""
import base64
import json
import os
from pathlib import Path

from .d2 import D2Error, test_database
from .preflight import canonical_json, safe_file
from .windows_acl import restrict_directory, verify_private


class EncryptedTestDelivery:
    """No plaintext file or overwrite; pending survives an uncertain publication."""
    def __init__(self, directory, *, encryption_key):
        root = test_database().parent
        directory = Path(directory)
        if directory.parent != root or not directory.is_dir() or directory.is_symlink() or directory.resolve() != directory:
            raise D2Error('Delivery must use an existing directory inside the disposable test root.')
        if getattr(directory.lstat(), 'st_file_attributes', 0) & 0x400:
            raise D2Error('Reparse delivery directories are forbidden.')
        if not isinstance(encryption_key, bytes) or len(encryption_key) != 32:
            raise D2Error('An externally retained 32-byte encryption key is required.')
        try:
            from cryptography.fernet import Fernet
        except ImportError:
            raise D2Error('Authenticated encryption support is unavailable; no plaintext fallback.') from None
        self.cipher = Fernet(base64.urlsafe_b64encode(encryption_key))
        if any(directory.iterdir()):
            verify_private(directory)  # Never silently repair permissions on an existing delivery.
        else:
            restrict_directory(directory)
        self.directory = directory
        self.pending = directory / 'd2.pending'
        self.final = directory / 'd2.bundle'

    def load(self):
        test_database()
        verify_private(self.directory)
        if self.pending.exists() and self.final.exists():
            raise D2Error('Ambiguous delivery files; manual investigation required.')
        path = self.final if self.final.exists() else self.pending
        if not path.exists():
            return None
        safe_file(path)
        verify_private(path)
        if path.stat().st_size > 2_000_000:
            raise D2Error('Encrypted bundle exceeds size limit.')
        return json.loads(self.cipher.decrypt(path.read_bytes()).decode())

    def stage(self, bundle):
        test_database(_allow_atomic=True)
        verify_private(self.directory)
        if self.final.exists():
            raise D2Error('Delivered bundle already exists; overwrite forbidden.')
        encrypted = self.cipher.encrypt(canonical_json(bundle).encode())
        descriptor = os.open(self.pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(encrypted); stream.flush(); os.fsync(stream.fileno())
        verify_private(self.pending)

    def publish(self):
        test_database()
        verify_private(self.directory)
        if self.final.exists():
            if self.pending.exists():
                raise D2Error('Ambiguous publication state; overwrite forbidden.')
            safe_file(self.final)
            verify_private(self.final)
            return
        safe_file(self.pending)
        verify_private(self.pending)
        if os.name != 'nt':
            raise D2Error('Publication is restricted to Windows no-overwrite rename.')
        os.rename(self.pending, self.final)  # Windows raises if destination exists.
