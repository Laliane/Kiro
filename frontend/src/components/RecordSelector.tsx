import { useState } from 'react'
import type { SimilarityResult } from '../types'
import { sendExternal, updateSelections } from '../api/client'

interface Props {
  sessionId: string
  results: SimilarityResult[]
  onReportRequest: () => void
}

export default function RecordSelector({ sessionId, results, onReportRequest }: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [sending, setSending] = useState(false)
  const [sendStatus, setSendStatus] = useState<string | null>(null)

  const toggle = async (recordId: string) => {
    const isSelected = selected.has(recordId)
    const add_ids = isSelected ? [] : [recordId]
    const remove_ids = isSelected ? [recordId] : []

    try {
      const res = await updateSelections(sessionId, add_ids, remove_ids)
      const next = new Set(res.selected_record_ids)
      setSelected(next)
    } catch (err) {
      console.error('Erro ao atualizar seleção', err)
    }
  }

  const handleSendExternal = async () => {
    setSending(true)
    setSendStatus(null)
    try {
      const res = await sendExternal(sessionId)
      setSendStatus(
        res.success
          ? `✅ ${res.sent_count} record(s) enviado(s) com sucesso.`
          : `❌ Falha ao enviar: ${res.message}`
      )
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Erro ao enviar para API externa.'
      setSendStatus(`❌ ${detail}`)
    } finally {
      setSending(false)
    }
  }

  if (results.length === 0) {
    return (
      <div className="p-4 text-gray-400 text-sm text-center">
        Nenhum resultado de similaridade disponível. Execute uma busca primeiro.
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <span className="text-sm font-medium text-gray-700">
          {selected.size} de {results.length} selecionado(s)
        </span>
        <div className="flex gap-2">
          <button
            onClick={onReportRequest}
            className="text-sm bg-indigo-600 text-white px-3 py-1.5 rounded-lg hover:bg-indigo-700 transition-colors"
          >
            Gerar Relatório
          </button>
          <button
            onClick={handleSendExternal}
            disabled={selected.size === 0 || sending}
            className="text-sm bg-green-600 text-white px-3 py-1.5 rounded-lg hover:bg-green-700 disabled:opacity-40 transition-colors"
          >
            {sending ? 'Enviando...' : 'Enviar para API'}
          </button>
        </div>
      </div>

      {sendStatus && (
        <div className="mx-4 mt-2 text-sm p-2 rounded-lg bg-gray-50 border text-gray-700">
          {sendStatus}
        </div>
      )}

      <div className="flex-1 overflow-y-auto divide-y">
        {results.map((r) => {
          const isChecked = selected.has(r.record.id)
          return (
            <div
              key={r.record.id}
              className={`p-4 cursor-pointer hover:bg-gray-50 transition-colors ${
                isChecked ? 'bg-blue-50' : ''
              }`}
              onClick={() => toggle(r.record.id)}
            >
              <div className="flex items-start gap-3">
                <input
                  type="checkbox"
                  checked={isChecked}
                  onChange={() => toggle(r.record.id)}
                  onClick={(e: React.MouseEvent) => e.stopPropagation()}
                  className="mt-1 h-4 w-4 text-blue-600 rounded"
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-mono text-gray-400 truncate">
                      {r.record.id}
                    </span>
                    <span
                      className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                        r.similarity_score >= 0.8
                          ? 'bg-green-100 text-green-700'
                          : r.similarity_score >= 0.6
                          ? 'bg-yellow-100 text-yellow-700'
                          : 'bg-red-100 text-red-700'
                      }`}
                    >
                      {(r.similarity_score * 100).toFixed(1)}%
                    </span>
                  </div>
                  {/* Top attributes */}
                  <div className="text-xs text-gray-600 space-y-0.5">
                    {Object.entries(r.record.attributes)
                      .slice(0, 4)
                      .map(([k, v]) => (
                        <span key={k} className="mr-3">
                          <span className="font-medium">{k}:</span> {String(v)}
                        </span>
                      ))}
                  </div>
                  {/* Top contributions */}
                  {r.attribute_contributions.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {r.attribute_contributions.slice(0, 3).map((c) => (
                        <span
                          key={c.attribute_name}
                          title={c.justification}
                          className="text-xs bg-indigo-50 text-indigo-700 px-1.5 py-0.5 rounded"
                        >
                          {c.attribute_name} ({(c.contribution_score * 100).toFixed(0)}%)
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
