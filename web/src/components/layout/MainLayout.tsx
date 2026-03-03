import { useEffect, useRef, useState } from 'react'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'
import { MessageList } from '../chat/MessageList'
import { InputPanel } from '../chat/InputPanel'
import { ReasoningPanelV2 } from '../reasoning/ReasoningPanelV2'
import { SearchOverlay } from '../search/SearchOverlay'
import { ModeSelector } from '../chat/ModeSelector'
import { LoginScreen } from '../auth/LoginScreen'
import { OnboardingFlow } from '../auth/OnboardingFlow'
import { useUIStore } from '../../stores/ui'
import { useChatStore } from '../../stores/chat'
import { EmptyState } from '../chat/EmptyState'
import { ErrorBoundary } from '../common/ErrorBoundary'
import { VoicePage } from '../../pages/VoicePage'
import { VisionPage } from '../../pages/VisionPage'
import { LogsPage } from '../../pages/LogsPage'
import { BrainPage } from '../../pages/BrainPage'
import { TerminalPage } from '../../pages/TerminalPage'
import { SettingsPage } from '../../pages/SettingsPage'
import { API_RAW } from '../../lib/env'
import { useModeAccent } from '../../hooks/useModeAccent'

const API = API_RAW

const PANEL_WIDTH_CLASS: Record<string, string> = {
  sidebar: 'w-80',
  half: 'w-[50vw]',
  fullscreen: '', // handled separately as overlay
  hidden: '',
}

export function MainLayout() {
  useModeAccent()
  const rightPanelVisible = useUIStore((s) => s.rightPanelVisible)
  const setRightPanelVisible = useUIStore((s) => s.setRightPanelVisible)
  const reasoningPanelSize = useUIStore((s) => s.reasoningPanelSize)
  const setReasoningPanelSize = useUIStore((s) => s.setReasoningPanelSize)
  const searchOpen = useUIStore((s) => s.searchOpen)
  const activePage = useUIStore((s) => s.activePage)
  const authenticated = useUIStore((s) => s.authenticated)
  const setAuthenticated = useUIStore((s) => s.setAuthenticated)
  const activeId = useChatStore((s) => s.activeId)
  const streamingThinking = useChatStore((s) => s.streamingThinking)
  const prevThinkingRef = useRef('')
  const [needsOnboarding, setNeedsOnboarding] = useState(false)

  // Auto-open reasoning panel the first time thinking content arrives in a stream
  useEffect(() => {
    if (streamingThinking && !prevThinkingRef.current) {
      setRightPanelVisible(true)
      if (reasoningPanelSize === 'hidden') {
        setReasoningPanelSize('sidebar')
      }
    }
    prevThinkingRef.current = streamingThinking
  }, [streamingThinking, setRightPanelVisible, reasoningPanelSize, setReasoningPanelSize])

  // Route to onboarding if no owner, skip login if no passphrase set
  useEffect(() => {
    fetch(`${API}/settings/auth/status`)
      .then((r) => r.json())
      .then((d) => {
        if (!d.has_owner) {
          setNeedsOnboarding(true)
        } else if (!d.passphrase_set) {
          setAuthenticated(true)
        }
      })
      .catch(() => setAuthenticated(true)) // API unreachable → let through
  }, [setAuthenticated])

  if (needsOnboarding) {
    return (
      <OnboardingFlow
        onComplete={() => {
          setNeedsOnboarding(false)
          setAuthenticated(true)
        }}
      />
    )
  }

  if (!authenticated) return <LoginScreen />

  const renderPage = () => {
    switch (activePage) {
      case 'voice': return <VoicePage />
      case 'vision': return <VisionPage />
      case 'logs': return <LogsPage />
      case 'brain': return <BrainPage />
      case 'terminal': return <TerminalPage />
      case 'settings': return <SettingsPage />
      case 'chat':
      default:
        return (
          <div className="flex flex-1 min-h-0">
            <div className="flex flex-1 flex-col min-w-0">
              {activeId ? (
                <>
                  <MessageList />
                  <InputPanel />
                </>
              ) : (
                <EmptyState />
              )}
            </div>
            {rightPanelVisible && reasoningPanelSize !== 'fullscreen' && reasoningPanelSize !== 'hidden' && (
              <aside
                aria-label="Reasoning"
                className={`${PANEL_WIDTH_CLASS[reasoningPanelSize]} border-l border-border flex-shrink-0 overflow-hidden`}
              >
                <ErrorBoundary>
                  <ReasoningPanelV2 />
                </ErrorBoundary>
              </aside>
            )}
            {reasoningPanelSize === 'fullscreen' && (
              <div className="fixed inset-0 z-50 bg-surface/95 backdrop-blur-sm flex flex-col">
                <ErrorBoundary>
                  <ReasoningPanelV2 />
                </ErrorBoundary>
              </div>
            )}
          </div>
        )
    }
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-surface">
      {activePage === 'chat' && (
        <aside aria-label="Conversations">
          <Sidebar />
        </aside>
      )}

      <main className="flex flex-1 flex-col min-w-0">
        <header>
          <TopBar />
        </header>
        {renderPage()}
      </main>

      {searchOpen && <SearchOverlay />}
      <ModeSelector />
    </div>
  )
}
