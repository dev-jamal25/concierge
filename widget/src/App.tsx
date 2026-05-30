import { type CSSProperties, type FormEvent, useEffect, useRef, useState } from "react"
import type { ChatResponse, WidgetConfig } from "./api"

function createConversationId() {
  if ("randomUUID" in crypto) {
    return crypto.randomUUID()
  }
  return "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (char) =>
    (
      Number(char) ^
      (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (Number(char) / 4)))
    ).toString(16),
  )
}

type Msg = { role: "user" | "assistant"; text: string }
type UIState = "loading" | "ready" | "error"

const S = {
  root: {
    display: "flex", flexDirection: "column", height: "95vh",
    fontFamily: "system-ui, -apple-system, sans-serif",
    fontSize: "14px", margin: 0, background: "#fff", overflow: "hidden",
  } as CSSProperties,
  header: {
    padding: "12px 16px", background: "#1a1a2e", color: "#fff",
    fontSize: "15px", fontWeight: 600, flexShrink: 0,
  } as CSSProperties,
  body: {
    flex: 1, overflowY: "auto", padding: "12px 14px",
    display: "flex", flexDirection: "column", gap: "6px",
  } as CSSProperties,
  footer: {
    padding: "8px 10px", borderTop: "1px solid #e5e5e5", flexShrink: 0,
  } as CSSProperties,
  userMsg: {
    background: "#1a1a2e", color: "#fff",
    borderRadius: "14px 14px 3px 14px",
    padding: "8px 12px", maxWidth: "80%", marginLeft: "auto",
    wordBreak: "break-word", lineHeight: 1.45,
  } as CSSProperties,
  agentMsg: {
    background: "#f0f0f0", color: "#111",
    borderRadius: "14px 14px 14px 3px",
    padding: "8px 12px", maxWidth: "80%",
    wordBreak: "break-word", lineHeight: 1.45,
  } as CSSProperties,
  typingMsg: {
    background: "#f0f0f0", color: "#888",
    borderRadius: "14px 14px 14px 3px",
    padding: "8px 14px", maxWidth: "60px", letterSpacing: "2px",
  } as CSSProperties,
  input: {
    flex: 1, padding: "8px 11px",
    border: "1px solid #d0d0d0", borderRadius: "6px",
    fontSize: "14px", outline: "none",
  } as CSSProperties,
  sendBtn: {
    padding: "8px 16px", background: "#1a1a2e", color: "#fff",
    border: "none", borderRadius: "6px", cursor: "pointer",
    fontSize: "14px", fontWeight: 500,
  } as CSSProperties,
  sendBtnDisabled: {
    padding: "8px 16px", background: "#b0b0c0", color: "#fff",
    border: "none", borderRadius: "6px", cursor: "not-allowed",
    fontSize: "14px", fontWeight: 500,
  } as CSSProperties,
  startBtn: {
    padding: "10px 20px", background: "#1a1a2e", color: "#fff",
    border: "none", borderRadius: "6px", cursor: "pointer",
    fontSize: "14px", fontWeight: 500, alignSelf: "flex-start",
  } as CSSProperties,
  centred: {
    flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
    color: "#999", padding: "24px",
  } as CSSProperties,
}

function App() {
  const [parentOrigin, setParentOrigin] = useState<string | null>(null)
  const parentOriginRef = useRef<string | null>(null)
  const [conversationId] = useState(createConversationId)
  const [config, setConfig] = useState<WidgetConfig | null>(null)
  const [accepted, setAccepted] = useState(false)
  const [message, setMessage] = useState("")
  const [messages, setMessages] = useState<Msg[]>([])
  const [uiState, setUiState] = useState<UIState>("loading")
  const [errorText, setErrorText] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to newest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, sending])

  // Timeout: if no bootstrap after 12s show an error
  useEffect(() => {
    const timer = setTimeout(() => {
      setUiState((prev) => {
        if (prev === "loading") {
          setErrorText("Could not connect to the chat service. Make sure the stack is running and the widget ID is correct.")
          return "error"
        }
        return prev
      })
    }, 12000)
    return () => clearTimeout(timer)
  }, [])

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (event.data?.type === "concierge.bootstrap") {
        setConfig(event.data.config as WidgetConfig)
        parentOriginRef.current = event.origin
        setParentOrigin(event.origin)
        setUiState("ready")
        return
      }

      if (event.origin !== parentOriginRef.current) return

      if (event.data?.type === "concierge.chat.response") {
        setSending(false)
        if (event.data.ok === true) {
          const payload = event.data.payload as ChatResponse
          const text =
            payload.reply?.trim() ||
            (payload.escalated ? "You've been connected with our team. Someone will follow up shortly." : "Message received.")
          setMessages((m) => [...m, { role: "assistant", text }])
        } else {
          setMessages((m) => [
            ...m,
            { role: "assistant", text: "Sorry, the service is temporarily unavailable. Please try again." },
          ])
        }
      }
    }
    window.addEventListener("message", onMessage)
    return () => window.removeEventListener("message", onMessage)
  }, [])

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!parentOrigin || !message.trim() || sending) return
    const text = message.trim()
    setMessage("")
    setMessages((m) => [...m, { role: "user", text }])
    setSending(true)
    window.parent.postMessage(
      { type: "concierge.chat", requestId: createConversationId(), conversation_id: conversationId, message: text },
      parentOrigin,
    )
  }

  const greeting = config?.greeting ?? "Concierge"

  if (uiState === "loading") {
    return (
      <main style={S.root}>
        <div style={S.header}>{greeting}</div>
        <div style={S.centred}>Connecting…</div>
      </main>
    )
  }

  if (uiState === "error") {
    return (
      <main style={S.root}>
        <div style={S.header}>{greeting}</div>
        <div style={{ ...S.centred, color: "#c00", textAlign: "center" }}>
          {errorText ?? "Unable to connect. Please refresh the page."}
        </div>
      </main>
    )
  }

  return (
    <main style={S.root}>
      <div style={S.header}>{greeting}</div>

      {!accepted ? (
        <div style={{ ...S.body, justifyContent: "center" }}>
          <p style={{ color: "#555", marginBottom: "16px", lineHeight: 1.5 }}>
            {config?.consent_notice ?? "By chatting, you agree to share this conversation with the site owner."}
          </p>
          <button type="button" onClick={() => setAccepted(true)} style={S.startBtn}>
            Start chat
          </button>
        </div>
      ) : (
        <>
          <div style={S.body}>
            {messages.length === 0 && !sending && (
              <p style={{ color: "#aaa", fontSize: "13px", textAlign: "center", marginTop: "12px" }}>
                Send a message to get started.
              </p>
            )}
            {messages.map((item, i) => (
              <div key={i} style={item.role === "user" ? S.userMsg : S.agentMsg}>
                {item.text}
              </div>
            ))}
            {sending && <div style={S.typingMsg}>•••</div>}
            <div ref={bottomRef} />
          </div>

          <form onSubmit={submit} style={S.footer}>
            <div style={{ display: "flex", gap: "7px" }}>
              <input
                aria-label="Message"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Type a message…"
                disabled={sending}
                style={S.input}
              />
              <button
                type="submit"
                disabled={sending || !message.trim()}
                style={sending || !message.trim() ? S.sendBtnDisabled : S.sendBtn}
              >
                Send
              </button>
            </div>
          </form>
        </>
      )}
    </main>
  )
}

export default App
