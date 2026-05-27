type TokenResponse = {
  token: string
  expires_in_seconds: number
}

const script = document.currentScript as HTMLScriptElement | null

if (script) {
  const widgetId = script.dataset.widgetId
  const position = script.dataset.position ?? "bottom-right"
  const apiBase = new URL(script.src).origin
  let iframe: HTMLIFrameElement | null = null
  let refreshTimer: number | undefined

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

  const bootstrap = (token: string) => {
    if (!iframe) {
      iframe = document.createElement("iframe")
      iframe.src = `${apiBase}/widget/?widget_id=${encodeURIComponent(widgetId ?? "")}`
      iframe.sandbox.add("allow-scripts", "allow-forms", "allow-same-origin")
      iframe.referrerPolicy = "strict-origin"
      positionIframe(iframe)
      document.body.appendChild(iframe)
    }
    iframe.onload = () => {
      iframe?.contentWindow?.postMessage(
        { type: "concierge.bootstrap", token },
        apiBase,
      )
    }
  }

  const refresh = async () => {
    if (!widgetId) {
      return
    }
    const data = await issueToken()
    bootstrap(data.token)
    window.clearTimeout(refreshTimer)
    refreshTimer = window.setTimeout(
      refresh,
      Math.max(data.expires_in_seconds - 30, 30) * 1000,
    )
  }

  refresh().catch(() => {
    console.warn("Concierge widget unavailable for this origin")
  })
}
