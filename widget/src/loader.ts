import { fetchWidgetConfig, sendChatMessage, type WidgetConfig } from "./api"

type TokenResponse = {
  token: string
  expires_in_seconds: number
}

type ChatRequestMessage = {
  type: "concierge.chat"
  requestId: string
  conversation_id: string
  message: string
}

const script = document.currentScript as HTMLScriptElement | null

if (script) {
  const widgetId = script.dataset.widgetId
  const position = script.dataset.position ?? "bottom-right"
  const apiBase = script.dataset.apiBase ?? new URL(script.src).origin
  let iframe: HTMLIFrameElement | null = null
  let currentToken: string | null = null
  let currentConfig: WidgetConfig | null = null
  let refreshTimer: number | undefined

  const isChatRequest = (value: unknown): value is ChatRequestMessage => {
    if (!value || typeof value !== "object") {
      return false
    }
    const data = value as Record<string, unknown>
    return (
      data.type === "concierge.chat" &&
      typeof data.requestId === "string" &&
      typeof data.conversation_id === "string" &&
      typeof data.message === "string"
    )
  }

  const issueToken = async (): Promise<TokenResponse> => {
    const response = await fetch(`${apiBase}/widget/token`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        widget_id: widgetId,
        origin: window.location.origin,
      }),
    })
    if (!response.ok) {
      throw new Error("Token issuance failed")
    }
    return response.json()
  }

  const loadConfig = (token: string) => fetchWidgetConfig(apiBase, token)

  const positionIframe = (target: HTMLIFrameElement) => {
    target.style.position = "fixed"
    target.style.bottom = "20px"
    target.style.width = "380px"
    target.style.height = "560px"
    target.style.border = "0"
    target.style.zIndex = "2147483647"
    if (position === "bottom-left") {
      target.style.left = "20px"
    } else {
      target.style.right = "20px"
    }
  }

  const postBootstrap = () => {
    if (!iframe?.contentWindow || !currentToken || !currentConfig) {
      return
    }
    iframe.contentWindow.postMessage(
      {
        type: "concierge.bootstrap",
        token: currentToken,
        config: currentConfig,
      },
      apiBase,
    )
  }

  const bootstrap = (token: string, config: WidgetConfig) => {
    currentToken = token
    currentConfig = config
    if (!iframe) {
      iframe = document.createElement("iframe")
      iframe.src = `${apiBase}/widget/?widget_id=${encodeURIComponent(widgetId ?? "")}`
      iframe.title = "Concierge chat"
      iframe.sandbox.add("allow-scripts", "allow-forms", "allow-same-origin")
      iframe.referrerPolicy = "strict-origin"
      positionIframe(iframe)
      iframe.addEventListener("load", postBootstrap)
      document.body.appendChild(iframe)
    }
    postBootstrap()
  }

  const refresh = async () => {
    if (!widgetId) {
      return
    }
    const data = await issueToken()
    const config = currentConfig ?? (await loadConfig(data.token))
    bootstrap(data.token, config)
    window.clearTimeout(refreshTimer)
    refreshTimer = window.setTimeout(
      refresh,
      Math.max(data.expires_in_seconds - 30, 30) * 1000,
    )
  }

  window.addEventListener("message", async (event) => {
    if (!iframe?.contentWindow || event.source !== iframe.contentWindow) {
      return
    }
    if (event.origin !== apiBase || !currentToken || !isChatRequest(event.data)) {
      return
    }

    try {
      const payload = await sendChatMessage(
        apiBase,
        currentToken,
        event.data.conversation_id,
        event.data.message,
      )
      iframe.contentWindow.postMessage(
        {
          type: "concierge.chat.response",
          requestId: event.data.requestId,
          ok: true,
          payload,
        },
        apiBase,
      )
    } catch {
      iframe.contentWindow.postMessage(
        {
          type: "concierge.chat.response",
          requestId: event.data.requestId,
          ok: false,
        },
        apiBase,
      )
    }
  })

  refresh().catch(() => {
    console.warn("Concierge widget unavailable for this origin")
  })
}
