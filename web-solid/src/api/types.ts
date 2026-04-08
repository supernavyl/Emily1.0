export interface ConversationSummary {
  id: string
  title: string
  created_at: string
  updated_at: string
  model: string | null
  provider: string | null
  skill_id: string | null
  pinned: boolean
  archived: boolean
  tags: string[]
  total_messages: number
  total_tokens_in: number
  total_tokens_out: number
  total_thinking_tokens: number
  total_cost_usd: number
  parent_id: string | null
  branch_from_message_id: string | null
}

export interface Message {
  id: string
  conversation_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  content_raw: string | null
  thinking_content: string | null
  model: string | null
  provider: string | null
  tokens_in: number
  tokens_out: number
  tokens_thinking: number
  cost_usd: number
  latency_ms: number | null
  first_token_ms: number | null
  created_at: string
  edited: boolean
  stopped: boolean
  rating: number
  version: number
  parent_message_id: string | null
}

export interface ModelSpec {
  key: string
  display: string
  provider: string
  model_id: string
  context: number
  thinking: boolean
  vision: boolean
  audio: boolean
  video: boolean
  input_usd: number
  output_usd: number
  speed: string
  tier: string
  default: boolean
  open_weights: boolean
  best_for: string[]
  notes: string
  reasoning_effort: string[]
}

export interface Skill {
  id: string
  name: string
  icon: string
  description: string
  enable_thinking: boolean
  enable_web_search: boolean
  enable_code_execution: boolean
  temperature: number
  built_in: boolean
}

export interface EmilyProfile {
  id: string
  name: string
  roles: Record<string, string>
}

export interface ProfileRole {
  key: string
  label: string
}

export interface SearchResult {
  conversation_id: string
  message_id: string
  title: string
  excerpt: string
  match_rank: number
}

export interface UsageData {
  tokens_in: number
  tokens_out: number
  tokens_thinking: number
  cost_usd: number
  latency_ms: number
  model_key: string
  provider: string
}

export interface StreamMeta {
  model_key: string
  model_id: string
  provider: string
  display: string
  mode_id?: string
  mode_display?: string
  mode_icon?: string
  reasoning_strategy?: string
}

export interface AppSettings {
  theme: string
  font_size: number
  default_model: string
  active_skill_id: string
  active_profile_id: string
  right_panel_visible: boolean
}

export const PROVIDER_COLORS: Record<string, string> = {
  anthropic: '#f59e0b',
  openai: '#22c55e',
  google: '#3b82f6',
  xai: '#14b8a6',
  deepseek: '#06b6d4',
  groq: '#f97316',
  mistral: '#ef4444',
  together: '#ec4899',
  openrouter: '#0ea5e9',
  ollama: '#10b981',
  llamacpp: '#14b8a6',
}

export const MODEL_CATEGORIES: Record<string, string[]> = {
  'Emily (Local Brain)': ['emily-fast', 'emily-smart', 'emily-reasoning', 'emily-deep-think', 'emily-code', 'emily-nano', 'emily-voice-fast', 'emily-vision'],
  'Thinking Models': ['claude-opus-4', 'o3', 'deepseek-r2', 'groq-deepseek-r1', 'kimi-k2-thinking', 'glm-4-7-thinking'],
  'Balanced': ['claude-sonnet-4-5', 'gpt-5', 'gemini-3-pro', 'grok-4-1', 'qwen3-235b'],
  'Fast': ['claude-haiku-4', 'gpt-4o', 'o4-mini', 'gemini-3-flash', 'groq-llama-70b', 'qwen3-72b', 'mistral-small-3'],
  'Code': ['codestral-2', 'deepseek-v3-2'],
  'Massive Context': ['gemini-3-pro', 'llama-4-scout', 'llama-4-maverick', 'gemini-2-5-pro'],
  'EU / Privacy': ['mistral-large-3', 'mistral-small-3'],
}
