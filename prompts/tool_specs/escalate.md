---
version: "1.0.0"
changelog: "1.0.0 (2026-05-28): Initial versioned release (T193)."
---

# Tool Spec — escalate

**Name**: `escalate`

**Description**: Flag this conversation for human follow-up. Use when the
visitor requests a human, or when you cannot resolve the query with the
available tools.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| reason | string | yes | Brief reason for escalation (e.g. "visitor requested human") |

## Response format

```json
{
  "escalated": true
}
```

## Usage notes

- After calling this tool, inform the visitor that a team member will follow up
  and end the turn.
- Do not continue the agent loop after escalating.
- This tool is idempotent — calling it twice on the same conversation is safe
  but unnecessary.
