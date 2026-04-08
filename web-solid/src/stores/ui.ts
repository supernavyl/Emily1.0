import { createStore } from 'solid-js/store'

export type AppPage = 'chat' | 'voice' | 'vision' | 'logs' | 'brain' | 'terminal' | 'settings'

export type ReasoningPanelSize = 'sidebar' | 'half' | 'fullscreen' | 'hidden'

interface UIState {
  theme: 'dark' | 'light'
  searchOpen: boolean
  modeSelectorOpen: boolean
  rightPanelVisible: boolean
  sidebarWidth: number
  activePage: AppPage
  authenticated: boolean
  reasoningPanelSize: ReasoningPanelSize
}

const PANEL_CYCLE: ReasoningPanelSize[] = ['sidebar', 'half', 'fullscreen', 'hidden']

const [uiState, setUIState] = createStore<UIState>({
  theme: 'dark',
  searchOpen: false,
  modeSelectorOpen: false,
  rightPanelVisible: true,
  sidebarWidth: 260,
  activePage: 'chat',
  authenticated: false,
  reasoningPanelSize: 'sidebar',
})

export { uiState }

export function toggleTheme(): void {
  setUIState('theme', (prev) => {
    const next = prev === 'dark' ? 'light' : 'dark'
    document.documentElement.classList.toggle('dark', next === 'dark')
    return next
  })
}

export function setSearchOpen(open: boolean): void {
  setUIState('searchOpen', open)
}

export function setModeSelectorOpen(open: boolean): void {
  setUIState('modeSelectorOpen', open)
}

export function toggleRightPanel(): void {
  setUIState('rightPanelVisible', (prev) => !prev)
}

export function setRightPanelVisible(visible: boolean): void {
  setUIState('rightPanelVisible', visible)
}

export function setSidebarWidth(w: number): void {
  setUIState('sidebarWidth', w)
}

export function setActivePage(page: AppPage): void {
  setUIState('activePage', page)
}

export function setAuthenticated(auth: boolean): void {
  setUIState('authenticated', auth)
}

export function setReasoningPanelSize(size: ReasoningPanelSize): void {
  setUIState({ reasoningPanelSize: size, rightPanelVisible: size !== 'hidden' })
}

export function cycleReasoningPanel(): void {
  const idx = PANEL_CYCLE.indexOf(uiState.reasoningPanelSize)
  const next = PANEL_CYCLE[(idx + 1) % PANEL_CYCLE.length]
  setUIState({ reasoningPanelSize: next, rightPanelVisible: next !== 'hidden' })
}
