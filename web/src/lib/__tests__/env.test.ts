import { describe, it, expect } from 'vitest'

describe('env (browser mode)', () => {
  it('detects non-Tauri environment', async () => {
    // Default jsdom has no __TAURI_INTERNALS__
    const { IS_TAURI, API_BASE, API_RAW } = await import('../env')
    expect(IS_TAURI).toBe(false)
    expect(API_BASE).toBe('')
    expect(API_RAW).toBe('/api')
  })
})
