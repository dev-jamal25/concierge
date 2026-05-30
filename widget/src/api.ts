export type WidgetConfig = {
  theme_config: Record<string, unknown>
  greeting: string
  persona_summary: string
  consent_notice: string
}

export type ChatResponse = {
  route: "spam" | "faq" | "lead_intent" | "escalate" | "agent" | "unavailable"
  reply?: string | null
  escalated: boolean
  retrieved_chunks: Array<{ cms_page_id: string; snippet: string }>
  capture_lead_status?: string | null
}

export async function fetchWidgetConfig(
  apiBaseUrl: string,
  token: string,
): Promise<WidgetConfig> {
  const response = await fetch(`${apiBaseUrl}/widget/config`, {
    headers: {
      authorization: `Bearer ${token}`,
    },
  })
  if (!response.ok) {
    throw new Error("Failed to load widget config")
  }
  return response.json()
}

export async function sendChatMessage(
  apiBaseUrl: string,
  token: string,
  conversationId: string,
  message: string,
): Promise<ChatResponse> {
  const response = await fetch(`${apiBaseUrl}/chat`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({ conversation_id: conversationId, message }),
  })
  if (!response.ok) {
    throw new Error("Chat endpoint unavailable")
  }
  return response.json()
}
