"""Named users and sign-in sessions.

- People sign up themselves (`POST /auth/signup`) and must confirm their email through a
  single-use link (`verification`) before they can sign in. Admins can also create
  accounts from the CLI (`python -m app.auth.cli`); those count as verified.
- Passwords are Argon2id hashes (`passwords`).
- A session is an opaque random token in the httpOnly `dp_session` cookie; the
  database stores only its SHA-256 (`sessions`).
- Routes use the dependencies in `app.auth.deps`.
"""
