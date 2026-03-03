import { create } from 'zustand'
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

  loadModels: () => Promise<void>
  loadSkills: () => Promise<void>
  loadModes: () => Promise<void>
  setActiveModel: (key: string) => void
  setActiveSkill: (id: string) => void
  setActiveMode: (id: string) => void
}

export const useModelsStore = create<ModelsState>((set) => ({
  models: {},
  providers: {},
  skills: {},
  modes: {},
  activeModel: 'auto',
  activeSkill: 'normal',
  activeMode: 'normal',

  loadModels: async () => {
    const [modelsRes, providersRes] = await Promise.all([
      api.models.list(),
      api.models.providers(),
    ])
    set({ models: modelsRes.models, providers: providersRes.providers })
  },

  loadSkills: async () => {
    const { skills } = await api.skills.list()
    set({ skills })
  },

  loadModes: async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/modes`)
      if (res.ok) {
        const data = await res.json()
        set({ modes: data.modes })
      }
    } catch {
      // Modes API not available yet — use empty
    }
  },

  setActiveModel: (key: string) => set({ activeModel: key }),
  setActiveSkill: (id: string) => set({ activeSkill: id }),
  setActiveMode: (id: string) => set({ activeMode: id }),
}))
