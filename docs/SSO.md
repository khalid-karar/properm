# Single sign-on (OpenID Connect)

PROPERM signs people in through your company identity provider (Microsoft Entra ID, Okta, Keycloak, Google Workspace, ADFS 2019+, any OIDC provider). It uses the authorization-code flow with PKCE, and checks the ID token's signature, issuer, audience, expiry and nonce before trusting anything.

1. At the provider, register a **web application** with the redirect URI `https://<your-server>/auth/sso/callback`. Note the client id and secret. Give it the scopes `openid email profile`.
2. On the server set:

| Variable | Meaning |
|---|---|
| `PROPERM_OIDC_ISSUER` | the provider's issuer URL (turns SSO on). Entra: `https://login.microsoftonline.com/<tenant>/v2.0` |
| `PROPERM_OIDC_CLIENT_ID`, `PROPERM_OIDC_CLIENT_SECRET` | from step 1 |
| `PROPERM_OIDC_REDIRECT_URI` | exactly the URI from step 1 |
| `PROPERM_OIDC_MATCH` | `email` (default) or `staff_id`: how a person is matched to a PROPERM user |
| `PROPERM_OIDC_CLAIM` | claim to match on (default `email`, or `preferred_username` for `staff_id`) |
| `PROPERM_OIDC_AUTO_CREATE` | `1` creates a STAFF user the first time an unknown person signs in. Default off: only people already in PROPERM (active) can sign in |
| `PROPERM_SSO_ONLY` | `1` turns off password sign-in for everyone except ADMIN (break-glass) |
| `PROPERM_UI_URL` | where the browser lands afterwards (default `/ui/`) |

Roles stay managed inside PROPERM. The provider only proves who the person is. Two-factor is the provider's job when SSO is used.

The Netlify pages and the server are on different addresses, so set `PROPERM_API` in `config.js` to the server and `PROPERM_UI_URL` to the Netlify address.

Not covered: SAML (use an OIDC bridge such as Keycloak in front of a SAML-only provider), group-to-role mapping, and automatic deactivation when someone leaves the provider (deactivate them in PROPERM, or use `PROPERM_SSO_ONLY` plus the provider's own offboarding, which stops new sign-ins; existing sessions end within the session lifetime).

Tested with a simulated provider (`tests/test_sso.py`), not against a live Entra/Okta tenant.
