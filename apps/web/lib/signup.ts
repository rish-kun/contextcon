/** Sign-up stays off until the API serves POST /auth/signup. Set NEXT_PUBLIC_SIGNUP_ENABLED=true to show it. */
export const SIGNUP_ENABLED = process.env.NEXT_PUBLIC_SIGNUP_ENABLED === "true";
