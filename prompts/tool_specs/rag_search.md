# Tool Spec — rag_search

**Name**: `rag_search`

**Description**: Search this tenant's published CMS content (knowledge base)
for chunks relevant to the visitor's query. Returns up to 5 ranked text
snippets with their source page ID.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| query | string | yes | The search query derived from the visitor's message |

## Response format

```json
[
  {
    "content": "<chunk text>",
    "cms_page_id": "<uuid>"
  }
]
```

## Usage notes

- Call with the visitor's question rephrased as a search query if needed.
- If the result list is empty, the knowledge base has no relevant published content.
- Do not call this tool more than twice per turn; prefer to synthesise from
  the first call's results.
