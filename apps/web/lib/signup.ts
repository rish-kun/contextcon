/**
 * Sign-up is on by default (the API serves `POST /auth/signup`). A deployment that turns
 * it off on the API (`AUTH_SIGNUP_ENABLED=false`) sets NEXT_PUBLIC_SIGNUP_ENABLED=false
 * so the home page and login page stop offering it.
 */
export const SIGNUP_ENABLED = process.env.NEXT_PUBLIC_SIGNUP_ENABLED !== "false";
