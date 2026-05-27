export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"

export type WidgetConfig = {
  theme_config: Record<string, unknown>
  greeting: string
  persona_summary: string
  consent_notice: string
}

export async function fetchWidgetConfig(token: string): Promise<WidgetConfig> {
  const response = await fetch(`${API_BASE_URL}/widget/config`, {
    headers: {
      authorization: `Bearer ${token}`,
    },
  })
  if (!response.ok) {
    throw new Error("Failed to load widget config")
  }
  return response.json()
}

export async function sendChatMessage(token: string, message: string) {
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({ message }),
  })
  if (!response.ok) {
    throw new Error("Chat endpoint unavailable")
  }
  return response.json()
}
