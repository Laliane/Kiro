import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AnalysisReportView from '../components/AnalysisReport'
import ChatInterface from '../components/ChatInterface'
import RecordSelector from '../components/RecordSelector'
import {
  closeSession,
  createSession,
  generateReport,
  runSearch,
} from '../api/client'
import type { AnalysisReport, SimilarityResult } from '../types'

type Tab = 'chat' | 'results' | 'report'

const INACTIVITY_TIMEOUT_MS = 30 * 60 * 1000 // 30 min

export default function ChatPage() {
  const navigate = useNavigate()
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('chat')
  const [results, setResults] = useState<SimilarityResult[]>([])
  const [report, setReport] = useState<AnalysisReport | null>(null)
  const [searching, setSearching] = useState(false)
  const [reportLoading, setReportLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inactivityTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Create session on mount
  useEffect(() => {
    createSession()
      .then((s) => setSessionId(s.id))
      .catch(() => {
        navigate('/login')
      })
    return () => {
      if (inactivityTimer.current) clearTimeout(inactivityTimer.current)
    }
  }, [navigate])

  // Inactivity timer — expire session after 30 min
  const resetInactivityTimer = () => {
    if (inactivityTimer.current) clearTimeout(inactivityTimer.current)
    inactivityTimer.current = setTimeout(() => {
      if (sessionId) closeSession(sessionId).catch(() => {})
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      navigate('/login')
    }, INACTIVITY_TIMEOUT_MS)
  }

  useEffect(() => {
    resetInactivityTimer()
    window.addEventListener('mousemove', resetInactivityTimer)
    window.addEventListener('keydown', resetInactivityTimer)
    return () => {
      window.removeEventListener('mousemove', resetInactivityTimer)
      window.removeEventListener('keydown', resetInactivityTimer)
    }
  }, [sessionId]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleSearchReady = async () => {
    if (!sessionId) return
    setSearching(true)
    setError(null)
    try {
      const res = await runSearch(sessionId)
      setResults(res)
      setTab('results')
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Erro ao executar busca de similaridade.'
      setError(detail)
    } finally {
      setSearching(false)
    }
  }

  const handleReportRequest = async () => {
    if (!sessionId) return
    setReportLoading(true)
    setError(null)
    try {
      const r = await generateReport(sessionId)
      setReport(r)
      setTab('report')
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Erro ao gerar relatório.'
      setError(detail)
    } finally {
      setReportLoading(false)
    }
  }

  const handleLogout = () => {
    if (sessionId) closeSession(sessionId).catch(() => {})
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    navigate('/login')
  }

  if (!sessionId) {
    return (
      <div className="min-h-screen flex items-center justify-center text-gray-500">
        Iniciando sessão...
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-100 flex flex-col">
      {/* Top bar */}
      <header className="bg-white border-b px-4 py-3 flex items-center justify-between shadow-sm">
        <h1 className="text-base font-semibold text-gray-800">LLM Consultant Advisor</h1>
        <div className="flex items-center gap-3">
          {searching && (
            <span className="text-xs text-blue-600 animate-pulse">Buscando...</span>
          )}
          {reportLoading && (
            <span className="text-xs text-indigo-600 animate-pulse">Gerando relatório...</span>
          )}
          <button
            onClick={handleLogout}
            className="text-sm text-gray-500 hover:text-red-600 transition-colors"
          >
            Sair
          </button>
        </div>
      </header>

      {error && (
        <div className="mx-4 mt-2 text-sm p-2 rounded-lg bg-red-50 border border-red-200 text-red-700">
          ⚠️ {error}
        </div>
      )}

      {/* Tab bar */}
      <div className="bg-white border-b flex px-4">
        {(['chat', 'results', 'report'] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              tab === t
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {t === 'chat' ? 'Chat' : t === 'results' ? `Resultados (${results.length})` : 'Relatório'}
          </button>
        ))}
      </div>

      {/* Main content */}
      <main className="flex-1 overflow-hidden">
        <div className="h-full max-w-4xl mx-auto bg-white shadow-sm" style={{ height: 'calc(100vh - 112px)' }}>
          {tab === 'chat' && (
            <ChatInterface
              sessionId={sessionId}
              onSearchReady={handleSearchReady}
            />
          )}
          {tab === 'results' && (
            <RecordSelector
              sessionId={sessionId}
              results={results}
              onReportRequest={handleReportRequest}
            />
          )}
          {tab === 'report' && report && (
            <AnalysisReportView sessionId={sessionId} report={report} />
          )}
          {tab === 'report' && !report && (
            <div className="p-8 text-center text-gray-400 text-sm">
              Nenhum relatório gerado ainda. Selecione records e clique em "Gerar Relatório".
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
