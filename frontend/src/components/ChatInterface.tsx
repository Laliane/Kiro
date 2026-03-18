import { useEffect, useRef, useState } from 'react'
import type { ChatMessage } from '../types'
import {
  confirmQueryItem,
  getMessages,
  sendMessage,
  submitQueryItem,
} from '../api/client'

interface Props {
  sessionId: string
  onSearchReady: () => void
}

export default function ChatInterface({ sessionId, onSearchReady }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [queryMode, setQueryMode] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    getMessages(sessionId).then(setMessages).catch(console.error)
  }, [sessionId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const addMessage = (msg: ChatMessage) => setMessages((prev: ChatMessage[]) => [...prev, msg])

  const handleSend = async () => {
    if (!input.trim() || loading) return
    const text = input.trim()
    setInput('')
    setLoading(true)

    // Optimistic user message
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      session_id: sessionId,
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
      metadata: {},
    }
    addMessage(userMsg)

    try {
      let reply: ChatMessage
      if (queryMode) {
        reply = await submitQueryItem(sessionId, text)
        setQueryMode(false)
      } else {
        reply = await sendMessage(sessionId, text)
      }
      addMessage(reply)
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Erro ao enviar mensagem.'
      addMessage({
        id: crypto.randomUUID(),
        session_id: sessionId,
        role: 'assistant',
        content: `⚠️ ${detail}`,
        timestamp: new Date().toISOString(),
        metadata: { type: 'error' },
      })
    } finally {
      setLoading(false)
    }
  }

  const handleConfirm = async () => {
    setLoading(true)
    try {
      const reply = await confirmQueryItem(sessionId)
      addMessage(reply)
      onSearchReady()
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Erro ao confirmar.'
      addMessage({
        id: crypto.randomUUID(),
        session_id: sessionId,
        role: 'assistant',
        content: `⚠️ ${detail}`,
        timestamp: new Date().toISOString(),
        metadata: { type: 'error' },
      })
    } finally {
      setLoading(false)
    }
  }

  const isConfirmationMsg = (msg: ChatMessage) =>
    msg.metadata?.type === 'attribute_confirmation'

  return (
    <div className="flex flex-col h-full">
      {/* Message list */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <p className="text-gray-400 text-sm text-center mt-8">
            Inicie uma conversa ou descreva o item que deseja consultar.
          </p>
        )}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[75%] rounded-xl px-4 py-2 text-sm whitespace-pre-wrap ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : msg.metadata?.type === 'error'
                  ? 'bg-red-50 text-red-700 border border-red-200'
                  : 'bg-gray-100 text-gray-800'
              }`}
            >
              {msg.content}
              {isConfirmationMsg(msg) && (
                <div className="mt-3 flex gap-2">
                  <button
                    onClick={handleConfirm}
                    disabled={loading}
                    className="bg-green-600 text-white px-3 py-1 rounded-lg text-xs hover:bg-green-700 disabled:opacity-50"
                  >
                    Confirmar
                  </button>
                  <button
                    onClick={() => setQueryMode(true)}
                    disabled={loading}
                    className="bg-yellow-500 text-white px-3 py-1 rounded-lg text-xs hover:bg-yellow-600 disabled:opacity-50"
                  >
                    Corrigir
                  </button>
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="border-t p-3 flex gap-2 items-end">
        <div className="flex-1 flex flex-col gap-1">
          {queryMode && (
            <span className="text-xs text-blue-600 font-medium">
              Modo: descrever item de consulta
            </span>
          )}
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e: React.KeyboardEvent<HTMLTextAreaElement>) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
            }}
            placeholder={
              queryMode
                ? 'Descreva o item em linguagem natural...'
                : 'Digite sua mensagem...'
            }
            rows={2}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div className="flex flex-col gap-1">
          <button
            onClick={() => setQueryMode((v: boolean) => !v)}
            title="Alternar modo de consulta"
            className={`px-3 py-2 rounded-lg text-xs font-medium border transition-colors ${
              queryMode
                ? 'bg-blue-100 border-blue-400 text-blue-700'
                : 'bg-white border-gray-300 text-gray-600 hover:bg-gray-50'
            }`}
          >
            Consulta
          </button>
          <button
            onClick={handleSend}
            disabled={loading || !input.trim()}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {loading ? '...' : 'Enviar'}
          </button>
        </div>
      </div>
    </div>
  )
}
