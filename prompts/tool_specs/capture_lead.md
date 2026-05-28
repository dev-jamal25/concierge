---
version: "1.0.0"
changelog: "1.0.0 (2026-05-28): Initial versioned release (T193)."
---

# Tool Spec — capture_lead

**Name**: `capture_lead`

**Description**: Record a visitor's contact details and stated purchase or
follow-up intent into the tenant's leads CRM.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| contact | string | yes | Visitor's email address or phone number |
| intent | string | yes | What the visitor wants (e.g. "get a quote for X") |
| name | string | no | Visitor's name if they provided it |

## Response format

```json
{
  "status": "captured" | "rate_limited_window" | "rate_limited_lifetime" | "invalid_input"
}
```

## Usage notes

- Always ask for `contact` before calling this tool. Do not invent contact details.
- If `status` is `rate_limited_*`, inform the visitor their request has been noted
  and the team will follow up, then stop calling this tool for the session.
- Call only once per lead intent; do not retry on the same session turn.
