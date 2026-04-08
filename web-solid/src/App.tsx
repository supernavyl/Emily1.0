import { onMount } from 'solid-js'
import { MainLayout } from './components/layout/MainLayout'
import { ErrorBoundary } from './components/common/ErrorBoundary'
import { loadConversations } from './stores/chat'
import { loadModels, loadSkills, loadModes } from './stores/models'

export default function App() {
  onMount(() => {
    void loadConversations()
    void loadModels()
    void loadSkills()
    void loadModes()
  })

  return (
    <ErrorBoundary>
      <MainLayout />
    </ErrorBoundary>
  )
}
