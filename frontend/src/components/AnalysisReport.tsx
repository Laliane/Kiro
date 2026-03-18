import { useState } from 'react'
import type { AnalysisReport } from '../types'
import { exportReport } from '../api/client'

interface Props {
  sessionId: string
  report: AnalysisReport
}

export default function AnalysisReportView({ sessionId, report }: Props) {
  const [exportStatus, setExportStatus] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)

  const handleExport = async (format: 'json' | 'pdf') => {
    setExporting(true)
    setExportStatus(null)
    try {
      const blob = await exportReport(sessionId, format)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `relatorio_${sessionId}.${format}`
      a.click()
      URL.revokeObjectURL(url)
      setExportStatus(`✅ Exportação ${format.toUpperCase()} concluída.`)
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        `Erro ao exportar ${format.toUpperCase()}.`
      setExportStatus(`❌ ${detail}`)
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto p-4 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">Relatório de Análise</h2>
        <div className="flex gap-2">
          <button
            onClick={() => handleExport('json')}
            disabled={exporting}
            className="text-sm bg-gray-700 text-white px-3 py-1.5 rounded-lg hover:bg-gray-800 disabled:opacity-50 transition-colors"
          >
            Exportar JSON
          </button>
          <button
            onClick={() => handleExport('pdf')}
            disabled={exporting}
            className="text-sm bg-red-600 text-white px-3 py-1.5 rounded-lg hover:bg-red-700 disabled:opacity-50 transition-colors"
          >
            Exportar PDF
          </button>
        </div>
      </div>

      {exportStatus && (
        <div className="text-sm p-2 rounded-lg bg-gray-50 border text-gray-700">
          {exportStatus}
        </div>
      )}

      {/* Confidence note */}
      {report.confidence_note && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 text-sm text-yellow-800">
          ⚠️ {report.confidence_note}
        </div>
      )}

      {/* Summary */}
      <section>
        <h3 className="text-sm font-semibold text-gray-600 uppercase tracking-wide mb-1">
          Resumo
        </h3>
        <p className="text-sm text-gray-800">{report.summary || '—'}</p>
      </section>

      {/* Patterns */}
      {report.patterns.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold text-gray-600 uppercase tracking-wide mb-1">
            Padrões Identificados
          </h3>
          <ul className="list-disc list-inside space-y-1">
            {report.patterns.map((p, i) => (
              <li key={i} className="text-sm text-gray-800">
                {p}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Differences */}
      {report.differences.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold text-gray-600 uppercase tracking-wide mb-1">
            Diferenças
          </h3>
          <ul className="list-disc list-inside space-y-1">
            {report.differences.map((d, i) => (
              <li key={i} className="text-sm text-gray-800">
                {d}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Recommendations */}
      {report.recommendations.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold text-gray-600 uppercase tracking-wide mb-1">
            Recomendações
          </h3>
          <div className="space-y-2">
            {report.recommendations.map((rec, i) => (
              <div key={i} className="bg-indigo-50 rounded-lg p-3 text-sm text-indigo-900">
                <p>{rec.text}</p>
                <p className="text-xs text-indigo-500 mt-1">
                  Referência: {rec.supporting_record_id}
                </p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Explainability */}
      {report.explainability.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold text-gray-600 uppercase tracking-wide mb-2">
            Explicabilidade
          </h3>
          <div className="space-y-3">
            {report.explainability.map((sr) => (
              <div key={sr.record.id} className="border rounded-lg p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-mono text-gray-500 truncate">
                    {sr.record.id}
                  </span>
                  <span className="text-xs font-semibold text-blue-700">
                    {(sr.similarity_score * 100).toFixed(1)}%
                  </span>
                </div>
                {sr.attribute_contributions.map((c) => (
                  <div key={c.attribute_name} className="flex items-start gap-2 text-xs mb-1">
                    <span className="font-medium text-gray-700 w-28 shrink-0">
                      {c.attribute_name}
                    </span>
                    <div className="flex-1">
                      <div className="flex items-center gap-1 mb-0.5">
                        <div className="flex-1 bg-gray-200 rounded-full h-1.5">
                          <div
                            className="bg-blue-500 h-1.5 rounded-full"
                            style={{ width: `${c.contribution_score * 100}%` }}
                          />
                        </div>
                        <span className="text-gray-500 w-8 text-right">
                          {(c.contribution_score * 100).toFixed(0)}%
                        </span>
                      </div>
                      <p className="text-gray-500">{c.justification}</p>
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </section>
      )}

      <p className="text-xs text-gray-400 text-right">
        Base de conhecimento: {report.knowledge_base_size} registro(s) •{' '}
        {new Date(report.generated_at).toLocaleString('pt-BR')}
      </p>
    </div>
  )
}
