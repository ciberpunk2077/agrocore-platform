"""No environment flag opens this guard; only an authenticated live CLI session."""
from contextvars import ContextVar
from contextlib import contextmanager

_active = ContextVar('agrocore_controlled_rehearsal', default=None)


def scoped_database(*, _allow_atomic=False):
    session = _active.get()
    if session is None:
        return None
    from .rehearsal_command import _Session
    if type(session) is not _Session:
        raise ValueError('Invalid rehearsal execution scope.')
    return session.validate(_allow_atomic=_allow_atomic)


@contextmanager
def execution_scope(session):
    # validate() requires a signed grant AND its durable consumption evidence.
    session.validate()
    token = _active.set(session)
    try:
        yield
    finally:
        _active.reset(token)
        session.revoke()
