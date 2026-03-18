import axios from 'axios'
import type {
  AnalysisReport,
  ChatMessage,
  Session,
  SimilarityResult,
  TokenPair,
} from '../types'

const api = axios.create({ baseURL: '/api' })

// Attach JWT to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Redirect to login on 401/403
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 || err.response?.status === 403) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

// Auth
export const login = (username: string, password: string): Promise<TokenPair> =>
  api.post<TokenPair>('/auth/login', { username, password }).then((r) => r.data)

export const refreshToken = (refresh_token: string): Promise<TokenPair> =>
  api.post<TokenPair>('/auth/refresh', { refresh_token }).then((r) => r.data)

// Sessions
export const createSession = (): Promise<Session> =>
  api.post<Session>('/sessions').then((r) => r.data)

export const closeSession = (sessionId: string): Promise<void> =>
  api.delete(`/sessions/${sessionId}`).then(() => undefined)

// Messages
export const sendMessage = (sessionId: string, message: string): Promise<ChatMessage> =>
  api.post<ChatMessage>(`/sessions/${sessionId}/messages`, { message }).then((r) => r.data)

export const getMessages = (sessionId: string): Promise<ChatMessage[]> =>
  api.get<ChatMessage[]>(`/sessions/${sessionId}/messages`).then((r) => r.data)

// Query Item
export const submitQueryItem = (sessionId: string, description: string): Promise<ChatMessage> =>
  api.post<ChatMessage>(`/sessions/${sessionId}/query-item`, { description }).then((r) => r.data)

export const confirmQueryItem = (sessionId: string): Promise<ChatMessage> =>
  api.post<ChatMessage>(`/sessions/${sessionId}/query-item/confirm`).then((r) => r.data)

// Search
export const runSearch = (
  sessionId: string,
  top_n = 10,
  threshold = 0.5
): Promise<SimilarityResult[]> =>
  api
    .post<SimilarityResult[]>(`/sessions/${sessionId}/search`, { top_n, threshold })
    .then((r) => r.data)

export const getResults = (sessionId: string): Promise<SimilarityResult[]> =>
  api.get<SimilarityResult[]>(`/sessions/${sessionId}/results`).then((r) => r.data)

// Selections
export const updateSelections = (
  sessionId: string,
  add_ids: string[],
  remove_ids: string[]
): Promise<{ selected_record_ids: string[]; count: number }> =>
  api
    .patch(`/sessions/${sessionId}/selections`, { add_ids, remove_ids })
    .then((r) => r.data)

// Report
export const generateReport = (sessionId: string): Promise<AnalysisReport> =>
  api.post<AnalysisReport>(`/sessions/${sessionId}/report`).then((r) => r.data)

export const exportReport = (sessionId: string, format: 'json' | 'pdf'): Promise<Blob> =>
  api
    .post(`/sessions/${sessionId}/export`, { format }, { responseType: 'blob' })
    .then((r) => r.data)

// Send external
export const sendExternal = (
  sessionId: string
): Promise<{ success: boolean; status_code: number | null; message: string; sent_count: number }> =>
  api.post(`/sessions/${sessionId}/send-external`).then((r) => r.data)
