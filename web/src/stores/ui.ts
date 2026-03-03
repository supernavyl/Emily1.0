import { create } from 'zustand'

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

  toggleTheme: () => void
  setSearchOpen: (open: boolean) => void
  setModeSelectorOpen: (open: boolean) => void
  toggleRightPanel: () => void
  setRightPanelVisible: (visible: boolean) => void
  setSidebarWidth: (w: number) => void
  setActivePage: (page: AppPage) => void
  setAuthenticated: (auth: boolean) => void
  setReasoningPanelSize: (size: ReasoningPanelSize) => void
  cycleReasoningPanel: () => void
}

const PANEL_CYCLE: ReasoningPanelSize[] = ['sidebar', 'half', 'fullscreen', 'hidden']

export const useUIStore = create<UIState>((set) => ({
  theme: 'dark',
  searchOpen: false,
  modeSelectorOpen: false,
  rightPanelVisible: true,
  sidebarWidth: 260,
  activePage: 'chat',
  authenticated: false,
  reasoningPanelSize: 'sidebar',

  toggleTheme: () =>
    set((s) => {
      const next = s.theme === 'dark' ? 'light' : 'dark'
      document.documentElement.classList.toggle('dark', next === 'dark')
      return { theme: next }
    }),

  setSearchOpen: (open) => set({ searchOpen: open }),
  setModeSelectorOpen: (open) => set({ modeSelectorOpen: open }),
  toggleRightPanel: () => set((s) => ({ rightPanelVisible: !s.rightPanelVisible })),
  setRightPanelVisible: (visible) => set({ rightPanelVisible: visible }),
  setSidebarWidth: (w) => set({ sidebarWidth: w }),
  setActivePage: (page) => set({ activePage: page }),
  setAuthenticated: (auth) => set({ authenticated: auth }),
  setReasoningPanelSize: (size) => set({
    reasoningPanelSize: size,
    rightPanelVisible: size !== 'hidden',
  }),
  cycleReasoningPanel: () => set((s) => {
    const idx = PANEL_CYCLE.indexOf(s.reasoningPanelSize)
    const next = PANEL_CYCLE[(idx + 1) % PANEL_CYCLE.length]
    return { reasoningPanelSize: next, rightPanelVisible: next !== 'hidden' }
  }),
}))
