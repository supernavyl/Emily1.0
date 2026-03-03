import { describe, it, expect, vi, beforeEach } from 'vitest'
import { api } from '../client'

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

function jsonResponse(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

beforeEach(() => {
  mockFetch.mockReset()
})

describe('api.conversations', () => {
  it('lists conversations', async () => {
    const data = { conversations: [{ id: '1', title: 'Test' }] }
    mockFetch.mockResolvedValueOnce(jsonResponse(data))

    const result = await api.conversations.list()
    expect(result.conversations).toHaveLength(1)
    expect(result.conversations[0].id).toBe('1')

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/conversations?include_archived=false',
      expect.objectContaining({ headers: expect.objectContaining({ 'Content-Type': 'application/json' }) }),
    )
  })

  it('creates a conversation', async () => {
    const conv = { id: '2', title: 'New' }
    mockFetch.mockResolvedValueOnce(jsonResponse(conv))

    const result = await api.conversations.create({ title: 'New' })
    expect(result.id).toBe('2')

    const [, init] = mockFetch.mock.calls[0]
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ title: 'New' })
  })

  it('deletes a conversation', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ ok: true }))

    await api.conversations.delete('abc')
    const [url, init] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/v1/conversations/abc')
    expect(init.method).toBe('DELETE')
  })

  it('throws on error response', async () => {
    mockFetch.mockResolvedValueOnce(
      new Response('Not found', { status: 404 }),
    )

    await expect(api.conversations.get('bad')).rejects.toThrow('404')
  })
})

describe('api.models', () => {
  it('lists models', async () => {
    const data = { models: { 'emily-fast': { display: 'Fast' } } }
    mockFetch.mockResolvedValueOnce(jsonResponse(data))

    const result = await api.models.list()
    expect(result.models['emily-fast'].display).toBe('Fast')
  })
})

describe('api.search', () => {
  it('encodes query params', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ results: [] }))

    await api.search('hello world')
    const [url] = mockFetch.mock.calls[0]
    expect(url).toContain('q=hello%20world')
  })
})
