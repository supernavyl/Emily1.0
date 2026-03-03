import { API_BASE } from '../lib/env'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${res.status}: ${body}`)
  }
  return res.json()
}

export const api = {
  conversations: {
    list: (includeArchived = false) =>
      request<{ conversations: import('./types').ConversationSummary[] }>(
        `/api/v1/conversations?include_archived=${includeArchived}`,
      ),
    create: (body: { title?: string; model?: string; skill_id?: string }) =>
      request<import('./types').ConversationSummary>('/api/v1/conversations', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    get: (id: string) =>
      request<{
        conversation: import('./types').ConversationSummary
        messages: import('./types').Message[]
      }>(`/api/v1/conversations/${id}`),
    patch: (id: string, body: Record<string, unknown>) =>
      request(`/api/v1/conversations/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      }),
    delete: (id: string) =>
      request(`/api/v1/conversations/${id}`, { method: 'DELETE' }),
    duplicate: (id: string) =>
      request<import('./types').ConversationSummary>(
        `/api/v1/conversations/${id}/duplicate`,
        { method: 'POST' },
      ),
    fork: (id: string, fromMessageId: string) =>
      request<import('./types').ConversationSummary>(
        `/api/v1/conversations/${id}/fork`,
        { method: 'POST', body: JSON.stringify({ from_message_id: fromMessageId }) },
      ),
  },
  messages: {
    rate: (id: string, rating: number) =>
      request(`/api/v1/messages/${id}/rate`, {
        method: 'POST',
        body: JSON.stringify({ rating }),
      }),
    edit: (id: string, content: string) =>
      request(`/api/v1/messages/${id}/edit`, {
        method: 'POST',
        body: JSON.stringify({ content }),
      }),
  },
  search: (q: string, limit = 20) =>
    request<{ results: import('./types').SearchResult[] }>(
      `/api/v1/search?q=${encodeURIComponent(q)}&limit=${limit}`,
    ),
  models: {
    list: () => request<{ models: Record<string, import('./types').ModelSpec> }>('/api/v1/models'),
    providers: () =>
      request<{ providers: Record<string, { available: boolean }> }>('/api/v1/models/providers'),
  },
  skills: {
    list: () => request<{ skills: Record<string, import('./types').Skill> }>('/api/v1/skills'),
    delete: (id: string) => request(`/api/v1/skills/${id}`, { method: 'DELETE' }),
  },
  profiles: {
    list: () =>
      request<{
        profiles: import('./types').EmilyProfile[]
        roles: import('./types').ProfileRole[]
      }>('/api/v1/profiles'),
  },
  settings: {
    get: () => request<import('./types').AppSettings>('/api/v1/settings'),
    patch: (body: Partial<import('./types').AppSettings>) =>
      request('/api/v1/settings', { method: 'PATCH', body: JSON.stringify(body) }),
  },
}
