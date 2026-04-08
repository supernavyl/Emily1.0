import { createStore } from 'solid-js/store'
import { api } from '../api/client'
import { API_BASE } from '../lib/env'
import type { ModelSpec, Skill } from '../api/types'

export interface ModeInfo {
  id: string
  name: string
  display: string
  icon: string
  description: string
  reasoning_strategy: string
  reasoning_depth: number
  enable_thinking: boolean
  built_in: boolean
}

interface ModelsState {
  models: Record<string, ModelSpec>
  providers: Record<string, { available: boolean }>
  skills: Record<string, Skill>
  modes: Record<string, ModeInfo>
  activeModel: string
  activeSkill: string
  activeMode: string
}

const [modelsState, setModelsState] = createStore<ModelsState>({
  models: {},
  providers: {},
  skills: {},
  modes: {},
  activeModel: 'auto',
  activeSkill: 'normal',
  activeMode: 'normal',
})

export { modelsState }

export async function loadModels(): Promise<void> {
  const [modelsRes, providersRes] = await Promise.all([
    api.models.list(),
    api.models.providers(),
  ])
  setModelsState({ models: modelsRes.models, providers: providersRes.providers })
}

export async function loadSkills(): Promise<void> {
  const { skills } = await api.skills.list()
  setModelsState('skills', skills)
}

export async function loadModes(): Promise<void> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/modes`)
    if (res.ok) {
      const data: { modes: Record<string, ModeInfo> } = await res.json()
      setModelsState('modes', data.modes)
    }
  } catch {
    // Modes API not available yet — use empty
  }
}

export function setActiveModel(key: string): void {
  setModelsState('activeModel', key)
}

export function setActiveSkill(id: string): void {
  setModelsState('activeSkill', id)
}

export function setActiveMode(id: string): void {
  setModelsState('activeMode', id)
}
