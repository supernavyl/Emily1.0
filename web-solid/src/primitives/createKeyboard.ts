import { onMount, onCleanup } from 'solid-js'
import { uiState, setSearchOpen, setModeSelectorOpen } from '../stores/ui'
import { createConversation } from '../stores/chat'

export function createKeyboard(): void {
  function handler(e: KeyboardEvent): void {
    const mod = e.metaKey || e.ctrlKey
    if (!mod) return

    switch (e.key.toLowerCase()) {
      case 'k':
        e.preventDefault()
        setSearchOpen(!uiState.searchOpen)
        break
      case 'm':
        e.preventDefault()
        setModeSelectorOpen(!uiState.modeSelectorOpen)
        break
      case 'n':
        e.preventDefault()
        void createConversation()
        break
    }
  }

  onMount(() => {
    window.addEventListener('keydown', handler)
  })

  onCleanup(() => {
    window.removeEventListener('keydown', handler)
  })
}
