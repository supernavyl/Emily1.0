import { useEffect } from 'react'
import { useUIStore } from '../stores/ui'
import { useChatStore } from '../stores/chat'

export function useKeyboardShortcuts() {
  const setSearchOpen = useUIStore((s) => s.setSearchOpen)
  const searchOpen = useUIStore((s) => s.searchOpen)
  const modeSelectorOpen = useUIStore((s) => s.modeSelectorOpen)
  const setModeSelectorOpen = useUIStore((s) => s.setModeSelectorOpen)
  const createConversation = useChatStore((s) => s.createConversation)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault()
        setSearchOpen(!searchOpen)
      }

      if ((e.ctrlKey || e.metaKey) && e.key === 'm') {
        e.preventDefault()
        setModeSelectorOpen(!modeSelectorOpen)
      }

      if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
        e.preventDefault()
        createConversation()
      }
    }

    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [searchOpen, setSearchOpen, modeSelectorOpen, setModeSelectorOpen, createConversation])
}
