import { createEffect, onMount, Show, Switch, Match } from 'solid-js'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'
import { MessageList } from '../chat/MessageList'
import { InputPanel } from '../chat/InputPanel'
import { EmptyState } from '../chat/EmptyState'
import { ErrorBoundary } from '../common/ErrorBoundary'
import { BrainPage } from '../../pages/BrainPage'
import { SettingsPage } from '../../pages/SettingsPage'
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
    <Show when={uiState.authenticated} fallback={
      <div
        class="flex items-center justify-center h-screen w-screen"
        style={{ background: 'oklch(0.18 0.02 185)', color: 'oklch(0.65 0.03 185)' }}
      >
        Authenticating...
      </div>
    }>
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
                <PagePlaceholder name="Voice" />
              </ErrorBoundary>
            </Match>
            <Match when={uiState.activePage === 'vision'}>
              <ErrorBoundary>
                <PagePlaceholder name="Vision" />
              </ErrorBoundary>
            </Match>
            <Match when={uiState.activePage === 'logs'}>
              <ErrorBoundary>
                <PagePlaceholder name="Logs" />
              </ErrorBoundary>
            </Match>
            <Match when={uiState.activePage === 'brain'}>
              <ErrorBoundary>
                <BrainPage />
              </ErrorBoundary>
            </Match>
            <Match when={uiState.activePage === 'terminal'}>
              <ErrorBoundary>
                <PagePlaceholder name="Terminal" />
              </ErrorBoundary>
            </Match>
            <Match when={uiState.activePage === 'settings'}>
              <ErrorBoundary>
                <SettingsPage />
              </ErrorBoundary>
            </Match>
          </Switch>
        </main>
      </div>
    </Show>
  )
}

function PagePlaceholder(props: { name: string }) {
  return (
    <div
      class="flex-1 flex items-center justify-center"
      style={{ color: 'oklch(0.50 0.04 185)', 'font-family': 'var(--font-display)', 'font-size': '1.5rem' }}
    >
      {props.name} — Coming Soon
    </div>
  )
}
