# Widget SPEC

Owner: D - Widget/Admin/CI

## Purpose

The widget is the visitor-facing embedded chat surface. Tenants paste a single
script tag into their site. The script validates the host origin through the API,
injects an iframe, and passes a short-lived widget JWT to the iframe with
`postMessage`.

## Architecture

- `src/loader.ts`: dependency-free loader script for host pages.
- `src/App.tsx`: React + Vite + TypeScript iframe app.
- `src/api.ts`: API calls for widget config and chat.
- The host page never exposes the JWT in a URL.
- The iframe does not read or write host-page DOM outside its own iframe element.

## Security Contract

- Loader reads `data-widget-id` and `window.location.origin`.
- Loader calls `POST /widget/token` with `{ widget_id, origin }`.
- API issues a JWT only when the widget exists, is enabled, and the origin is in
  the tenant's `allowed_origins`.
- Token lifetime is capped at 5 minutes.
- Loader refreshes before expiry.
- Token is delivered to the iframe via `concierge.bootstrap` postMessage.

## Current Scope

- Basic iframe chat UI with consent notice.
- Widget config fetch from `/widget/config`.
- Chat call is wired to `/chat`, which is owned by Owner B and may be unavailable
  until that slice lands.
