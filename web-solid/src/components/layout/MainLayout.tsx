import { createEffect, onMount, Show, Switch, Match } from 'solid-js'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'
import { MessageList } from '../chat/MessageList'
import { InputPanel } from '../chat/InputPanel'
import { EmptyState } from '../chat/EmptyState'
import { ErrorBoundary } from '../common/ErrorBoundary'
import { LoginScreen } from '../auth/LoginScreen'
import { SearchOverlay } from '../search/SearchOverlay'
import { ModeSelector } from '../chat/ModeSelector'
import { BrainPage } from '../../pages/BrainPage'
import { SettingsPage } from '../../pages/SettingsPage'
import { VoicePage } from '../../pages/VoicePage'
import { VisionPage } from '../../pages/VisionPage'
import { LogsPage } from '../../pages/LogsPage'
import { TerminalPage } from '../../pages/TerminalPage'
import {
  uiState, setAuthenticated, setRightPanelVisible, setReasoningPanelSize,
} from '../../stores/ui'
import { chatState } from '../../stores/chat'
import { createModeAccent } from '../../primitives/createModeAccent'
import { createKeyboard } from '../../primitives/createKeyboard'
import { API_RAW } from '../../lib/env'

export function MainLayout() {
  createModeAccent()
  createKeyboard()

  let prevThinking = ''

  // Auto-open reasoning panel when thinking content arrives
  createEffect(() => {
    const thinking = chatState.streamingThinking
    if (thinking && !prevThinking) {
      setRightPanelVisible(true)
      if (uiState.reasoningPanelSize === 'hidden') {
        setReasoningPanelSize('sidebar')
      }
    }
    prevThinking = thinking
  })

  // Auth check on mount
  onMount(() => {
    fetch(`${API_RAW}/settings/auth/status`)
      .then((r) => r.json())
      .then((d: { passphrase_set?: boolean; has_owner?: boolean }) => {
        if (!d.passphrase_set || !d.has_owner) {
          setAuthenticated(true)
        }
      })
      .catch(() => setAuthenticated(true))
  })

  return (
    <Show when={uiState.authenticated} fallback={<LoginScreen />}>
      <div class="flex h-screen w-screen overflow-hidden" style={{ background: 'oklch(0.18 0.02 185)' }}>
        <Show when={uiState.activePage === 'chat'}>
          <aside>
            <Sidebar />
          </aside>
        </Show>

        <main class="flex flex-1 flex-col min-w-0">
          <header>
            <TopBar />
          </header>

          <Switch fallback={
            <div class="flex flex-1 min-h-0">
              <div class="flex flex-1 flex-col min-w-0">
                <Show when={chatState.activeId} fallback={<EmptyState />}>
                  <MessageList />
                  <InputPanel />
                </Show>
              </div>
            </div>
          }>
            <Match when={uiState.activePage === 'chat'}>
              <div class="flex flex-1 min-h-0">
                <div class="flex flex-1 flex-col min-w-0">
                  <Show when={chatState.activeId} fallback={<EmptyState />}>
                    <MessageList />
                    <InputPanel />
                  </Show>
                </div>
              </div>
            </Match>
            <Match when={uiState.activePage === 'voice'}>
              <ErrorBoundary>
                <VoicePage />
              </ErrorBoundary>
            </Match>
            <Match when={uiState.activePage === 'vision'}>
              <ErrorBoundary>
                <VisionPage />
              </ErrorBoundary>
            </Match>
            <Match when={uiState.activePage === 'logs'}>
              <ErrorBoundary>
                <LogsPage />
              </ErrorBoundary>
            </Match>
            <Match when={uiState.activePage === 'brain'}>
              <ErrorBoundary>
                <BrainPage />
              </ErrorBoundary>
            </Match>
            <Match when={uiState.activePage === 'terminal'}>
              <ErrorBoundary>
                <TerminalPage />
              </ErrorBoundary>
            </Match>
            <Match when={uiState.activePage === 'settings'}>
              <ErrorBoundary>
                <SettingsPage />
              </ErrorBoundary>
            </Match>
          </Switch>
        </main>

        {/* Overlays */}
        <Show when={uiState.searchOpen}>
          <SearchOverlay />
        </Show>
        <ModeSelector />
      </div>
    </Show>
  )
}
