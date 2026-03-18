// Domain types mirroring backend Pydantic models

export interface ChatMessage {
  id: string
  session_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: string
  metadata: Record<string, unknown>
}

export interface AttributeContribution {
  attribute_name: string
  contribution_score: number
  justification: string
}

export interface Record {
  id: string
  source_row_hash: string
  attributes: Record<string, unknown>
  embedding: number[]
  created_at: string
  updated_at: string
}

export interface SimilarityResult {
  record: Record
  similarity_score: number
  attribute_contributions: AttributeContribution[]
}

export interface Recommendation {
  text: string
  supporting_record_id: string
}

export interface AnalysisReport {
  id: string
  session_id: string
  generated_at: string
  summary: string
  patterns: string[]
  differences: string[]
  recommendations: Recommendation[]
  explainability: SimilarityResult[]
  knowledge_base_size: number
  confidence_note: string | null
}

export interface Session {
  id: string
  consultant_id: string
  created_at: string
  last_activity_at: string
  status: 'active' | 'expired' | 'closed'
  query_item: unknown | null
  selected_record_ids: string[]
  similarity_results: SimilarityResult[]
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
}
