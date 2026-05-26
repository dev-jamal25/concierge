import { type FormEvent, useEffect, useState } from "react"
import { fetchWidgetConfig, sendChatMessage, type WidgetConfig } from "./api"

function App() {
  const [token, setToken] = useState<string | null>(null)
  const [config, setConfig] = useState<WidgetConfig | null>(null)
  const [accepted, setAccepted] = useState(false)
  const [message, setMessage] = useState("")
  const [messages, setMessages] = useState<string[]>([])
  const [status, setStatus] = useState("Waiting for widget token")

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (event.data?.type !== "concierge.bootstrap") {
        return
      }
      setToken(event.data.token)
    }
    window.addEventListener("message", onMessage)
    return () => window.removeEventListener("message", onMessage)
  }, [])

  useEffect(() => {
    if (!token) {
      return
    }
    fetchWidgetConfig(token)
      .then((nextConfig) => {
        setConfig(nextConfig)
        setStatus("Ready")
      })
      .catch(() => setStatus("Service temporarily unavailable"))
  }, [token])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!token || !message.trim()) {
      return
    }
    const visitorMessage = message.trim()
    setMessage("")
    setMessages((current) => [...current, `You: ${visitorMessage}`])
    try {
      const reply = await sendChatMessage(token, visitorMessage)
      setMessages((current) => [
        ...current,
        `Concierge: ${reply.reply ?? "Thanks, I received your message."}`,
      ])
    } catch {
      setMessages((current) => [
        ...current,
        "Concierge: Service temporarily unavailable.",
      ])
    }
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
