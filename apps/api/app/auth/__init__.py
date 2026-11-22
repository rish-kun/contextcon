"""Named users and sign-in sessions.

- Accounts are created from the CLI (`python -m app.auth.cli`); there is no sign-up.
- Passwords are Argon2id hashes (`passwords`).
- A session is an opaque random token in the httpOnly `dp_session` cookie; the
  database stores only its SHA-256 (`sessions`).
- Routes use the dependencies in `app.auth.deps`.
"""
