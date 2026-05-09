"""Thread-local current-user storage so signal handlers can attribute changes
to the user that triggered them.

Used by:
  - CurrentUserMiddleware (sets the user on each request)
  - signals.py (reads the user when logging change-log entries)

This is a single-process Django + waitress app on a desktop, so a thread-local
is fine. If the app ever moves to async or multi-process workers, revisit.
"""

from __future__ import annotations

import threading

_local = threading.local()


def set_current_user(user) -> None:
    _local.user = user


def get_current_user():
    return getattr(_local, "user", None)


def clear_current_user() -> None:
    _local.user = None
