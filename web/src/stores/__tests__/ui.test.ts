import { describe, it, expect, beforeEach } from 'vitest'
import { useUIStore } from '../ui'

describe('useUIStore', () => {
  beforeEach(() => {
    // Reset store to defaults
    useUIStore.setState({
      theme: 'dark',
      searchOpen: false,
      rightPanelVisible: true,
      sidebarWidth: 260,
      activePage: 'chat',
      authenticated: false,
    })
  })

  it('has correct initial defaults', () => {
    const state = useUIStore.getState()
    expect(state.theme).toBe('dark')
    expect(state.searchOpen).toBe(false)
    expect(state.rightPanelVisible).toBe(true)
    expect(state.activePage).toBe('chat')
    expect(state.authenticated).toBe(false)
  })

  it('toggles right panel', () => {
    useUIStore.getState().toggleRightPanel()
    expect(useUIStore.getState().rightPanelVisible).toBe(false)

    useUIStore.getState().toggleRightPanel()
    expect(useUIStore.getState().rightPanelVisible).toBe(true)
  })

  it('sets active page', () => {
    useUIStore.getState().setActivePage('voice')
    expect(useUIStore.getState().activePage).toBe('voice')

    useUIStore.getState().setActivePage('brain')
    expect(useUIStore.getState().activePage).toBe('brain')
  })

  it('sets search open state', () => {
    useUIStore.getState().setSearchOpen(true)
    expect(useUIStore.getState().searchOpen).toBe(true)

    useUIStore.getState().setSearchOpen(false)
    expect(useUIStore.getState().searchOpen).toBe(false)
  })

  it('sets authenticated state', () => {
    useUIStore.getState().setAuthenticated(true)
    expect(useUIStore.getState().authenticated).toBe(true)
  })

  it('sets sidebar width', () => {
    useUIStore.getState().setSidebarWidth(300)
    expect(useUIStore.getState().sidebarWidth).toBe(300)
  })
})
