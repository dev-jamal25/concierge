# Admin SPEC

Owner: D - Widget/Admin/CI

## Purpose

The admin app is a Streamlit interface for tenant admins. It uses the FastAPI
backend and the existing session token issued by `/auth/login`. It does not
implement custom authentication.

## Pages

- `app.py`: API base URL and bearer token entry for local development.
- `pages/1_dashboard.py`: tenant overview.
- `pages/2_cms.py`: placeholder for Owner B CMS APIs.
- `pages/3_leads.py`: placeholder for Owner B leads APIs.
- `pages/4_settings.py`: persona/theme display, guardrails display, allowed
  origins management.
- `pages/5_embed_snippet.py`: embed snippet generator.

## API Surface

- `GET /admin/tenant`
- `PUT /admin/tenant`
- `GET /admin/guardrails`
- `PUT /admin/guardrails`
- `GET /admin/origins`
- `POST /admin/origins`
- `DELETE /admin/origins/{origin_id}`

## Boundaries

- CMS and leads business logic remains Owner B.
- Platform guardrails remain locked; tenant admins can only edit tenant-level
  guardrail configuration.
- Tenant identity comes from the signed session token, not from request bodies.
