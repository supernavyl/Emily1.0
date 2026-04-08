import { createEffect } from 'solid-js'
import { modelsState } from '../stores/models'
import { getModeTheme } from '../lib/mode-themes'

export function createModeAccent(): void {
  createEffect(() => {
    const theme = getModeTheme(modelsState.activeSkill)
    const el = document.documentElement
    el.style.setProperty('--color-mode-accent', theme.accent)
    el.style.setProperty('--color-mode-glow', theme.glow)
    el.style.setProperty('--mode-gradient', theme.gradient)
  })
}
