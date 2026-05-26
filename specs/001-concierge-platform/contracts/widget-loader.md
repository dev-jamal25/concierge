# Widget Loader Contract

**Slice**: D (Widget / Admin / CI)
**Loader URL**: `https://<api-host>/widget.js` (served from API or MinIO)
**Status**: Draft v1.0

The loader script is the single artifact a tenant pastes into their HTML.
This document is the contract the loader and the host page MUST honour.

---

## Embed snippet (what the host pastes)

```html
<script
  src="https://api.concierge.example.com/widget.js"
  data-widget-id="wgt_pub_a8K3...zQ"
  data-position="bottom-right"
  async
></script>
```

### Required attributes

| Attribute | Required | Purpose |
|-----------|----------|---------|
| `src` | yes | Loader URL — versioned by query string when rolled |
| `data-widget-id` | yes | Public widget identifier (`widgets.public_id`) |
| `async` | recommended | Don't block host page render |

### Optional attributes

| Attribute | Default | Allowed values |
|-----------|---------|----------------|
| `data-position` | `bottom-right` | `bottom-right`, `bottom-left` |
| `data-locale` | `en` | `en` (only English in v1.0) |

Any other `data-*` attributes MUST be ignored by the loader; they are
reserved for future use.

---

## Loader behaviour

On script load, the loader MUST:

1. **Read its own `data-*` attributes** from the executing `<script>`
   element via `document.currentScript`.
2. **Read the host page's origin** via `window.location.origin`.
3. **POST `/widget/token`** with body
   `{ widget_id, origin }`. Receive `{ token, expires_in_seconds }`.
4. **Inject an `<iframe>`** into the page with:
   - `src` = `https://<api-host>/widget/`. The iframe page receives
     the token via `postMessage` after `iframe.onload` (NOT via URL
     query string — JWTs MUST NOT be logged in URLs).
   - Styling matching `data-position`.
   - `sandbox="allow-scripts allow-forms allow-same-origin"`.
   - `referrerpolicy="strict-origin"`.
5. **Refresh the token** before expiry: schedule a refresh
   `(expires_in_seconds - 30)` seconds after issuance. On refresh
   failure (network or 403), close the widget and surface a clean
   "service unavailable" message to the visitor.

The loader MUST NOT:

- Read or write cookies, localStorage, or any host-page state.
- Make any network calls to anything other than the configured API
  host.
- Render any of its own UI on the host page outside the injected
  iframe.

---

## CSP / framing contract

For a tenant whose `allowed_origins` = `[https://acme.example.com,
https://shop.acme.example.com]`, the API serves:

- **`Access-Control-Allow-Origin`** echoes the request's `Origin`
  header if it matches one of `allowed_origins`, else `null`.
- **`Content-Security-Policy: frame-ancestors`** for `/widget/`
  pages is `https://acme.example.com https://shop.acme.example.com`.
- **Origin validation** is performed server-side on EVERY chat
  request — a token issued for `acme.example.com` sent from
  `shop.example.com` is rejected with 403 even if the token is
  otherwise valid.

Wildcards (`*.acme.example.com`) are NOT supported in v1.0; each
exact origin must be listed.

---

## Token contract

The widget JWT is signed with Ed25519 (key in Vault) and has the
following claims:

```json
{
  "iss": "concierge",
  "aud": "widget",
  "sub": "<widget.public_id>",
  "tenant_id": "<tenants.id UUID>",
  "widget_id": "<widgets.id UUID>",
  "origin": "<allowed origin issued for>",
  "visitor_session": "<random ID>",
  "iat": 1716624000,
  "exp": 1716624300,
  "kid": "<vault-key-id>"
}
```

The server uses ONLY the `tenant_id` claim to determine tenancy.
Any field in a request body or URL claiming a different tenant is
ignored and the request is rejected with 403.

**Lifetime**: ≤ 5 minutes (`expires_in_seconds ≤ 300`).

---

## Iframe ↔ host page communication

The injected iframe and the loader exchange only:

| Direction | Message type | Purpose |
|-----------|-------------|---------|
| Loader → Iframe | `concierge.bootstrap` | Hand over the token after iframe load |
| Iframe → Loader | `concierge.resize` | Request a height change |
| Iframe → Loader | `concierge.close` | Visitor closes the widget |

`postMessage` MUST verify `event.origin` matches the configured API
host on the iframe side, and `event.source === iframe.contentWindow`
on the loader side.

The widget MUST NEVER read or write anything on the host page DOM
beyond its own iframe element.

---

## Failure modes — visitor-visible behaviour

| Failure | Visitor sees | Server behaviour |
|---------|--------------|------------------|
| Token issuance fails (404 unknown widget) | Loader logs a warning and stays silent — no UI rendered | Audit-logged (warn) |
| Token issuance fails (403 origin mismatch) | Loader logs a warning and stays silent | Audit-logged |
| Chat 503 (LLM unavailable, after retries) | "Service temporarily unavailable" message in the widget; widget remains open | Conversation auto-flagged escalated |
| Token expired mid-conversation | Widget shows reconnect spinner; loader refreshes once | Normal |
| Tenant erasure in flight | Widget shows a clean error; future requests fail closed | `/chat` returns 409 |

---

## Loader compatibility

- **Browsers**: latest two stable versions of Chrome, Firefox, Safari,
  Edge.
- **No dependencies**: the loader is a single vanilla JS file. The
  React widget runs inside the iframe, NOT on the host page.
- **Size budget**: loader ≤ 5 KB gzipped.

---

## Versioning

The loader is versioned via the `src` URL: `widget.js?v=1`, `?v=2`,
etc. A breaking change in the loader contract requires a new version
in the URL the snippet uses. Tenants paste a versioned snippet from
their admin UI; old versions of the loader continue to be served for
a deprecation window of 90 days.
