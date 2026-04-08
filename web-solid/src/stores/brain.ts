import { createStore, produce } from 'solid-js/store'
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
  entries: unknown[]
  token_count: number
  session_id: string
}

export interface BrainEvent {
  ts: number
  cat: string
  kind: string
  data: Record<string, unknown>
}

interface BrainState {
  status: SystemStatus | null
  agents: Agent[]
  models: Record<string, ModelInfo>
  workingMemory: WorkingMemory | null
  episodicSessions: EpisodicSession[]
  episodicTotal: number
  emotionHistory: Record<string, number>[]
  profiles: unknown | null
  skills: Record<string, unknown>
  auditEntries: unknown[]
  selfImprovement: unknown | null

  // WebSocket real-time state
  wsConnected: boolean
  events: BrainEvent[]
}

const MAX_EVENTS = 500
const MAX_EMOTION_HISTORY = 60

const [brainState, setBrainState] = createStore<BrainState>({
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
  wsConnected: false,
  events: [],
})

export { brainState }

export function pushEvents(newEvents: BrainEvent[]): void {
  setBrainState('events', produce((events) => {
    events.push(...newEvents)
    if (events.length > MAX_EVENTS) events.splice(0, events.length - MAX_EVENTS)
  }))

  // Update FSM state from real-time events
  const lastFsm = newEvents.findLast((e) => e.cat === 'fsm' && e.kind === 'transition')
  if (lastFsm && brainState.status) {
    const current = brainState.status
    setBrainState('status', {
      ...current,
      fsm_state: (lastFsm.data['to'] as string) || current.fsm_state,
      fsm_history: [
        ...current.fsm_history,
        [lastFsm.data['from'] as string, lastFsm.data['to'] as string] as [string, string],
      ].slice(-20),
    })
  }
}

export function clearEvents(): void {
  setBrainState('events', [])
}

export function setWsConnected(connected: boolean): void {
  setBrainState('wsConnected', connected)
}

export async function pollStatus(): Promise<void> {
  try {
    const res = await fetch(`${API_RAW}/status`)
    if (!res.ok) return
    const data: Record<string, unknown> = await res.json()
    const status: SystemStatus = {
      fsm_state: (data['fsm_state'] as string) || ((data['fsm'] as Record<string, unknown>)?.['state'] as string) || 'IDLE',
      uptime_s: (data['uptime_s'] as number) || 0,
      resources: (data['resources'] as SystemResources) || {} as SystemResources,
      emotional_state: (data['emotional_state'] as Record<string, number>) || {},
      fsm_history: (data['fsm_history'] as [string, string][]) || ((data['fsm'] as Record<string, unknown>)?.['history'] as [string, string][]) || [],
      metrics: (data['metrics'] as Record<string, number>) || {},
    }
    setBrainState('emotionHistory', produce((history) => {
      history.push({ ...status.emotional_state })
      if (history.length > MAX_EMOTION_HISTORY) history.splice(0, history.length - MAX_EMOTION_HISTORY)
    }))
    setBrainState('status', status)
  } catch {
    // Status endpoint unavailable
  }
}

export async function pollAgents(): Promise<void> {
  try {
    const res = await fetch(`${API_RAW}/agents`)
    if (!res.ok) return
    const data: unknown = await res.json()
    setBrainState('agents', Array.isArray(data) ? data as Agent[] : ((data as Record<string, unknown>)['agents'] as Agent[]) || [])
  } catch {
    // Agents endpoint unavailable
  }
}

export async function loadBrainModels(): Promise<void> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/models`)
    if (!res.ok) return
    const data: Record<string, unknown> = await res.json()
    setBrainState('models', (data['models'] as Record<string, ModelInfo>) || data as Record<string, ModelInfo>)
  } catch {
    // Models endpoint unavailable
  }
}

export async function loadMemory(): Promise<void> {
  try {
    const [wRes, eRes] = await Promise.all([
      fetch(`${API_RAW}/memory/working`),
      fetch(`${API_RAW}/memory/episodic?n=10`),
    ])
    if (wRes.ok) {
      const w: WorkingMemory = await wRes.json()
      setBrainState('workingMemory', w)
    }
    if (eRes.ok) {
      const e: Record<string, unknown> = await eRes.json()
      setBrainState(
        'episodicSessions',
        Array.isArray(e) ? e as EpisodicSession[] : (e['sessions'] as EpisodicSession[]) || [],
      )
      setBrainState(
        'episodicTotal',
        (e['total_count'] as number) || (Array.isArray(e) ? e.length : 0),
      )
    }
  } catch {
    // Memory endpoint unavailable
  }
}

export async function loadProfiles(): Promise<void> {
  try {
    const [pRes, sRes] = await Promise.all([
      fetch(`${API_BASE}/api/v1/profiles`),
      fetch(`${API_BASE}/api/v1/skills`),
    ])
    if (pRes.ok) setBrainState('profiles', await pRes.json())
    if (sRes.ok) {
      const data: Record<string, unknown> = await sRes.json()
      setBrainState('skills', (data['skills'] as Record<string, unknown>) || data)
    }
  } catch {
    // Profiles endpoint unavailable
  }
}

export async function loadAudit(): Promise<void> {
  try {
    const res = await fetch(`${API_RAW}/security/audit?n=50`)
    if (!res.ok) return
    const data: unknown = await res.json()
    setBrainState('auditEntries', Array.isArray(data) ? data : ((data as Record<string, unknown>)['entries'] as unknown[]) || [])
  } catch {
    // Audit endpoint unavailable
  }
}

export async function loadSelfImprovement(): Promise<void> {
  try {
    const res = await fetch(`${API_RAW}/self-improvement`)
    if (!res.ok) return
    setBrainState('selfImprovement', await res.json())
  } catch {
    // Self-improvement endpoint unavailable
  }
}

export async function loadEmotionHistory(): Promise<void> {
  // Emotion history is populated incrementally by pollStatus.
  // This function exists for API parity — it triggers an initial status poll.
  await pollStatus()
}

export async function loadWorkingMemory(): Promise<void> {
  try {
    const res = await fetch(`${API_RAW}/memory/working`)
    if (!res.ok) return
    const w: WorkingMemory = await res.json()
    setBrainState('workingMemory', w)
  } catch {
    // Working memory endpoint unavailable
  }
}
