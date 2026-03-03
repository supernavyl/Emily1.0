import { useEffect } from 'react'
import { MainLayout } from './components/layout/MainLayout'
import { useChatStore } from './stores/chat'
import { useModelsStore } from './stores/models'
import { useKeyboardShortcuts } from './hooks/useKeyboard'

export default function App() {
  const loadConversations = useChatStore((s) => s.loadConversations)
  const loadModels = useModelsStore((s) => s.loadModels)
  const loadSkills = useModelsStore((s) => s.loadSkills)
  const loadModes = useModelsStore((s) => s.loadModes)

  useKeyboardShortcuts()

  useEffect(() => {
    loadConversations()
    loadModels()
    loadSkills()
    loadModes()
  }, [loadConversations, loadModels, loadSkills, loadModes])

  return <MainLayout />
}
