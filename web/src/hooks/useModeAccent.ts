import { useEffect } from 'react'
import { useModelsStore } from '../stores/models'
import { getModeTheme } from '../lib/mode-themes'

export function useModeAccent() {
  const activeSkill = useModelsStore((s) => s.activeSkill)

  useEffect(() => {
    const theme = getModeTheme(activeSkill)
    const root = document.documentElement
    root.style.setProperty('--color-mode-accent', theme.accent)
    root.style.setProperty('--color-mode-glow', theme.glow)
    root.style.setProperty('--mode-gradient', theme.gradient)
  }, [activeSkill])
}
