import { useState, useEffect } from 'react'
import { useBrainStore } from '../stores/brain'
import { BrainTabs, type BrainTab } from '../components/brain/BrainTabs'
import { NeuralOverview } from '../components/brain/NeuralOverview'
import { EmotionalCortex } from '../components/brain/EmotionalCortex'
import { CognitiveProcesses } from '../components/brain/CognitiveProcesses'
import { MemoryArchitecture } from '../components/brain/MemoryArchitecture'
import { ModelFleet } from '../components/brain/ModelFleet'
import { PersonalityMatrix } from '../components/brain/PersonalityMatrix'

export function BrainPage() {
  const [activeTab, setActiveTab] = useState<BrainTab>('neural')
  const pollStatus = useBrainStore((s) => s.pollStatus)
  const pollAgents = useBrainStore((s) => s.pollAgents)
  const loadModels = useBrainStore((s) => s.loadModels)
  const loadMemory = useBrainStore((s) => s.loadMemory)
  const loadProfiles = useBrainStore((s) => s.loadProfiles)

  useEffect(() => {
    // Initial loads
    pollStatus()
    pollAgents()
    loadModels()
    loadMemory()
    loadProfiles()

    // Polling
    const statusInterval = setInterval(pollStatus, 3000)
    const memoryInterval = setInterval(loadMemory, 10000)
    return () => {
      clearInterval(statusInterval)
      clearInterval(memoryInterval)
    }
  }, [pollStatus, pollAgents, loadModels, loadMemory, loadProfiles])

  const renderTab = () => {
    switch (activeTab) {
      case 'neural': return <NeuralOverview />
      case 'emotional': return <EmotionalCortex />
      case 'cognitive': return <CognitiveProcesses />
      case 'memory': return <MemoryArchitecture />
      case 'fleet': return <ModelFleet />
      case 'personality': return <PersonalityMatrix />
    }
  }

  return (
    <div className="flex flex-1 flex-col min-h-0">
      <BrainTabs active={activeTab} onChange={setActiveTab} />
      <div className="flex-1 overflow-y-auto">
        {renderTab()}
      </div>
    </div>
  )
}
