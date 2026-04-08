import { createSignal, Switch, Match } from 'solid-js'
import { BrainTabs, type BrainTab } from '../components/brain/BrainTabs'
import { NeuralOverview } from '../components/brain/NeuralOverview'
import { EventStream } from '../components/brain/EventStream'
import { EmotionalCortex } from '../components/brain/EmotionalCortex'
import { CognitiveProcesses } from '../components/brain/CognitiveProcesses'
import { MemoryArchitecture } from '../components/brain/MemoryArchitecture'
import { ModelFleet } from '../components/brain/ModelFleet'
import { PersonalityMatrix } from '../components/brain/PersonalityMatrix'
import { BrainChat } from '../components/brain/BrainChat'
import { createBrainWS } from '../primitives/createBrainWS'
import { createPolling } from '../primitives/createPolling'
import {
  pollStatus, pollAgents, loadBrainModels, loadMemory, loadProfiles,
} from '../stores/brain'

export function BrainPage() {
  const [activeTab, setActiveTab] = createSignal<BrainTab>('neural')

  // WebSocket for real-time brain events
  createBrainWS()

  // Polling for structural data (WS handles real-time events)
  createPolling(pollStatus, 10_000)
  createPolling(pollAgents, 30_000)
  createPolling(loadBrainModels, 30_000)
  createPolling(loadMemory, 30_000)
  createPolling(loadProfiles, 30_000)

  const specimenId = () => {
    if (typeof window !== 'undefined') {
      return window.location.hostname.slice(0, 8).toUpperCase().padEnd(8, '0')
    }
    return '00000000'
  }

  return (
    <div class="flex flex-1 flex-col min-h-0 relative" style={{ background: 'var(--color-surface)' }}>
      {/* Grid-paper background */}
      <div
        class="absolute inset-0 pointer-events-none data-lab-grid"
        style={{ opacity: '0.15' }}
        aria-hidden="true"
      />
      {/* Specimen ID */}
      <div
        class="absolute top-1 left-2 z-10 text-[9px] font-mono pointer-events-none select-none"
        style={{ color: 'var(--color-readout-dim)', 'letter-spacing': '0.06em' }}
        aria-hidden="true"
      >
        SID:{specimenId()}
      </div>

      <BrainTabs active={activeTab()} onChange={setActiveTab} />

      <div class="flex-1 overflow-y-auto relative z-0">
        <Switch fallback={
          <div
            class="flex-1 flex items-center justify-center h-full"
            style={{
              color: 'var(--color-readout-dim)',
              'font-family': 'var(--font-mono)',
              'font-size': '12px',
            }}
          >
            {activeTab().toUpperCase()} -- Coming Soon
          </div>
        }>
          <Match when={activeTab() === 'neural'}>
            <NeuralOverview />
          </Match>
          <Match when={activeTab() === 'emotional'}>
            <EmotionalCortex />
          </Match>
          <Match when={activeTab() === 'cognitive'}>
            <CognitiveProcesses />
          </Match>
          <Match when={activeTab() === 'memory'}>
            <MemoryArchitecture />
          </Match>
          <Match when={activeTab() === 'fleet'}>
            <ModelFleet />
          </Match>
          <Match when={activeTab() === 'personality'}>
            <PersonalityMatrix />
          </Match>
          <Match when={activeTab() === 'stream'}>
            <EventStream />
          </Match>
          <Match when={activeTab() === 'chat'}>
            <BrainChat />
          </Match>
        </Switch>
      </div>
    </div>
  )
}
