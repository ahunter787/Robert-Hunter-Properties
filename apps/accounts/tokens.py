"""Invitation tokens.

An invitation is a password-set link. It is built from Django's
``PasswordResetTokenGenerator`` so the same hardened primitives apply, with two
deliberate differences (ADR-004):

* a distinct ``key_salt``, so an invitation token can never be replayed as a
  password-reset token (or the reverse);
* ``is_active`` is part of the signed value, so deactivating an invited account
  immediately kills its outstanding link.

Single use is inherited: the parent already hashes the password, so the token
stops verifying the moment a password is set (and again once the invitee logs in,
because ``last_login`` changes).

Invitations and password resets share one expiry window,
``settings.PASSWORD_RESET_TIMEOUT``, because Django hardcodes that setting inside
``check_token``; having two windows would mean duplicating security-sensitive
verification logic.
"""

from django.contrib.auth.tokens import PasswordResetTokenGenerator


class InvitationTokenGenerator(PasswordResetTokenGenerator):
    """Token for the "set your password" invitation link."""

    key_salt = "apps.accounts.tokens.InvitationTokenGenerator"

    def _make_hash_value(self, user, timestamp):
        return f"{super()._make_hash_value(user, timestamp)}{user.is_active}"


invitation_token_generator = InvitationTokenGenerator()
