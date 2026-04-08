/**
 * Environment detection for Tauri vs browser contexts.
 *
 * In dev mode, Vite's proxy handles routing:
 *   /api/v1/*  → http://127.0.0.1:8001/api/v1/*  (pass-through)
 *   /api/*     → http://127.0.0.1:8001/*          (strips /api prefix)
 *
 * In production Tauri builds there is no proxy, so we need absolute URLs
 * pointing directly at the Emily API.
 */

export const IS_TAURI = '__TAURI_INTERNALS__' in window

export const PROD_TAURI = IS_TAURI && !import.meta.env.DEV

/** Base for routes that include /api/v1 (pass-through in both modes). */
export const API_BASE = PROD_TAURI ? 'http://127.0.0.1:8001' : ''

/**
 * Base for routes mounted without /api prefix (audio, memory, status, etc.).
 * In dev, Vite proxy rewrites /api/audio → /audio, so frontend uses /api/audio.
 * In production Tauri, there's no rewrite — hit /audio directly.
 */
export const API_RAW = PROD_TAURI ? 'http://127.0.0.1:8001' : '/api'

/**
 * Bearer token for API authentication.
 * Dev: read from Vite env (VITE_EMILY_API_SECRET in web/.env).
 * Prod Tauri: read from EMILY_API_SECRET injected into the process environment.
 */
export const API_SECRET: string = import.meta.env.VITE_EMILY_API_SECRET ?? ''

/** Standard auth headers — include in every fetch call to the API. */
export function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (API_SECRET) {
    headers['Authorization'] = `Bearer ${API_SECRET}`
  }
  return headers
}
