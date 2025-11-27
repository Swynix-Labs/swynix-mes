"""
Utilities that harden Frappe's session handling for MES.

This guards against cases where the session user is stored as ``None`` (string)
or removed from the ``User`` table, which previously caused the desk to fail
with ``User None is disabled`` validations.
"""

from __future__ import annotations

import functools
import logging
from typing import Optional

import frappe
from frappe.sessions import Session

LOGGER = logging.getLogger(__name__)


def _should_fallback_to_guest(user: Optional[str]) -> bool:
	"""Return True when the provided user value is effectively unusable."""
	if not user:
		return True

	user_str = str(user).strip()
	if not user_str:
		return True

	if user_str.lower() == "none":
		return True

	if not frappe.db.exists("User", user_str):
		return True

	return False


def _patch_validate_user():
	"""
	Monkey patch :meth:`frappe.sessions.Session.validate_user`
	so it gracefully falls back to Guest sessions whenever a
	broken session (user ``None``) is encountered.
	"""

	original_validate = Session.validate_user

	@functools.wraps(original_validate)
	def safe_validate(self: Session):
		if _should_fallback_to_guest(self.user):
			LOGGER.warning("Invalid session user '%s', falling back to Guest", self.user)
			self.start_as_guest()
			return

		return original_validate(self)

	# Avoid double patching
	if getattr(Session.validate_user, "_swynix_guard", False):
		return

	safe_validate._swynix_guard = True  # type: ignore[attr-defined]
	Session.validate_user = safe_validate  # type: ignore[assignment]


def cleanup_invalid_sessions():
	"""
	Delete session rows that point at removed/invalid users so they
	cannot break future requests.
	"""

	invalid_users = frappe.db.sql(
		"""
		select sid from `tabSessions`
		where coalesce(user, '') = ''
		   or lower(user) = 'none'
		   or user not in (select name from `tabUser`)
		""",
		pluck=True,
	)

	if not invalid_users:
		return

	LOGGER.warning("Removing %s invalid session(s)", len(invalid_users))
	frappe.db.sql("delete from `tabSessions` where sid in %(sids)s", {"sids": tuple(invalid_users)})
	frappe.db.commit()


def apply_session_guards():
	"""Public entrypoint to apply all runtime guards."""
	_patch_validate_user()


