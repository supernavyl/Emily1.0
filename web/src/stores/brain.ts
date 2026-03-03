import { create } from 'zustand'
import { API_BASE, API_RAW } from '../lib/env'

export interface SystemResources {
  cpu_percent: number
  ram_used_gb: number
  ram_total_gb: number
  ram_percent?: number
  vram_used_mb: number
  vram_total_mb: number
}

export interface SystemStatus {
  fsm_state: string
  uptime_s: number
  resources: SystemResources
  emotional_state: Record<string, number>
  fsm_history: [string, string][]
  metrics: Record<string, number>
}

export interface Agent {
  name: string
  type: string
  role: string
  status: string
}

export interface ModelInfo {
  display: string
  provider: string
  model_id: string
  context: number
  thinking: boolean
  vision: boolean
  speed: string
  tier: string
}

export interface EpisodicSession {
  id: string
  timestamp: string
  topics: string[]
  emotional_tone: string
  summary: string
}

export interface WorkingMemory {
  entries: any[]
  token_count: number
  session_id: string
}

interface BrainState {
  status: SystemStatus | null
  agents: Agent[]
  models: Record<string, ModelInfo>
  workingMemory: WorkingMemory | null
  episodicSessions: EpisodicSession[]
  episodicTotal: number
  emotionHistory: Record<string, number>[]
  profiles: any | null
  skills: Record<string, any>
  auditEntries: any[]
  selfImprovement: any | null

  pollStatus: () => Promise<void>
  pollAgents: () => Promise<void>
  loadModels: () => Promise<void>
  loadMemory: () => Promise<void>
  loadProfiles: () => Promise<void>
  loadAudit: () => Promise<void>
  loadSelfImprovement: () => Promise<void>
}

const MAX_EMOTION_HISTORY = 60

export const useBrainStore = create<BrainState>((set, get) => ({
  status: null,
  agents: [],
  models: {},
  workingMemory: null,
  episodicSessions: [],
  episodicTotal: 0,
  emotionHistory: [],
  profiles: null,
  skills: {},
  auditEntries: [],
  selfImprovement: null,

  pollStatus: async () => {
    try {
      const res = await fetch(`${API_RAW}/status`)
      if (!res.ok) return
      const data = await res.json()
      const status: SystemStatus = {
        fsm_state: data.fsm_state || data.fsm?.state || 'IDLE',
        uptime_s: data.uptime_s || 0,
        resources: data.resources || {},
        emotional_state: data.emotional_state || {},
        fsm_history: data.fsm_history || data.fsm?.history || [],
        metrics: data.metrics || {},
      }
      const prev = get().emotionHistory
      const next = [...prev, { ...status.emotional_state }]
      if (next.length > MAX_EMOTION_HISTORY) next.splice(0, next.length - MAX_EMOTION_HISTORY)
      set({ status, emotionHistory: next })
    } catch {}
  },

  pollAgents: async () => {
    try {
      const res = await fetch(`${API_RAW}/agents`)
      if (!res.ok) return
      const data = await res.json()
      set({ agents: Array.isArray(data) ? data : data.agents || [] })
    } catch {}
  },

  loadModels: async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/models`)
      if (!res.ok) return
      const data = await res.json()
      set({ models: data.models || data || {} })
    } catch {}
  },

  loadMemory: async () => {
    try {
      const [wRes, eRes] = await Promise.all([
        fetch(`${API_RAW}/memory/working`),
        fetch(`${API_RAW}/memory/episodic?n=10`),
      ])
      if (wRes.ok) {
        const w = await wRes.json()
        set({ workingMemory: w })
      }
      if (eRes.ok) {
        const e = await eRes.json()
        set({
          episodicSessions: Array.isArray(e) ? e : e.sessions || [],
          episodicTotal: e.total_count || (Array.isArray(e) ? e.length : 0),
        })
      }
    } catch {}
  },

  loadProfiles: async () => {
    try {
      const [pRes, sRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/profiles`),
        fetch(`${API_BASE}/api/v1/skills`),
      ])
      if (pRes.ok) set({ profiles: await pRes.json() })
      if (sRes.ok) {
        const data = await sRes.json()
        set({ skills: data.skills || data || {} })
      }
    } catch {}
  },

  loadAudit: async () => {
    try {
      const res = await fetch(`${API_RAW}/security/audit?n=50`)
      if (!res.ok) return
      const data = await res.json()
      set({ auditEntries: Array.isArray(data) ? data : data.entries || [] })
    } catch {}
  },

  loadSelfImprovement: async () => {
    try {
      const res = await fetch(`${API_RAW}/self-improvement`)
      if (!res.ok) return
      set({ selfImprovement: await res.json() })
    } catch {}
  },
}))
