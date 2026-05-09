"""Stash the current request.user in a thread-local so signal handlers can
attribute model changes to the user."""

from __future__ import annotations

from .audit import clear_current_user, set_current_user


class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            set_current_user(user)
        else:
            set_current_user(None)
        try:
            return self.get_response(request)
        finally:
            clear_current_user()
