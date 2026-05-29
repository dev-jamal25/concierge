import { type FormEvent, useEffect, useRef, useState } from "react"
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

function App() {
  const [token, setToken] = useState<string | null>(null)
  const [parentOrigin, setParentOrigin] = useState<string | null>(null)
  const parentOriginRef = useRef<string | null>(null)
  const [conversationId] = useState(createConversationId)
  const [config, setConfig] = useState<WidgetConfig | null>(null)
  const [accepted, setAccepted] = useState(false)
  const [message, setMessage] = useState("")
  const [messages, setMessages] = useState<string[]>([])
  const [status, setStatus] = useState("Waiting for widget token")

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (event.data?.type === "concierge.bootstrap") {
        setToken(event.data.token)
        setConfig(event.data.config)
        parentOriginRef.current = event.origin
        setParentOrigin(event.origin)
        setStatus("Ready")
        return
      }

      if (event.origin !== parentOriginRef.current) {
        return
      }

      if (
        event.data?.type === "concierge.chat.response" &&
        event.data.ok === true
      ) {
        const payload = event.data.payload as ChatResponse
        setMessages((current) => [
          ...current,
          `Concierge: ${payload.reply ?? "Thanks, I received your message."}`,
        ])
        return
      }

      if (
        event.data?.type === "concierge.chat.response" &&
        event.data.ok === false
      ) {
        setMessages((current) => [
          ...current,
          "Concierge: Service temporarily unavailable.",
        ])
      }
    }
    window.addEventListener("message", onMessage)
    return () => window.removeEventListener("message", onMessage)
  }, [])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!token || !parentOrigin || !message.trim()) {
      return
    }
    const visitorMessage = message.trim()
    setMessage("")
    setMessages((current) => [...current, `You: ${visitorMessage}`])
    window.parent.postMessage(
      {
        type: "concierge.chat",
        requestId: createConversationId(),
        conversation_id: conversationId,
        message: visitorMessage,
      },
      parentOrigin,
    )
  }

  return (
    <main>
      <h1>Concierge</h1>
      <p>{config?.greeting ?? status}</p>
      {!accepted ? (
        <section>
          <p>
            {config?.consent_notice ??
              "By chatting, you agree to share this conversation with the site owner."}
          </p>
          <button type="button" onClick={() => setAccepted(true)}>
            Start chat
          </button>
        </section>
      ) : (
        <section>
          <div aria-live="polite">
            {messages.map((item) => (
              <p key={item}>{item}</p>
            ))}
          </div>
          <form onSubmit={submit}>
            <input
              aria-label="Message"
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder="Type your message"
            />
            <button type="submit">Send</button>
          </form>
        </section>
      )}
    </main>
  )
}

export default App
