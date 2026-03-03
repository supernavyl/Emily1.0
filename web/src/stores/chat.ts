import { create } from 'zustand'
import { api } from '../api/client'
import { streamChat } from '../api/sse'
import type { ReasoningStepEvent, SkillProgressEvent, SearchEvent } from '../api/sse'
import type { ConversationSummary, Message, UsageData, StreamMeta } from '../api/types'

export interface ReasoningStep {
  event_type: string
  step_name: string
  model: string
  content: string
  metadata: Record<string, unknown>
  timestamp: number
}

interface ChatState {
  conversations: ConversationSummary[]
  activeId: string | null
  messages: Message[]
  isStreaming: boolean
  streamingText: string
  streamingThinking: string
  streamMeta: StreamMeta | null
  lastUsage: UsageData | null
  abortController: AbortController | null

  // Reasoning state
  reasoningSteps: ReasoningStep[]
  skillProgress: SkillProgressEvent[]
  activeMode: string

  // Web search state
  searchStatus: SearchEvent | null
  searchSources: Array<{ title: string; url: string }> | null

  loadConversations: () => Promise<void>
  selectConversation: (id: string) => Promise<void>
  createConversation: (title?: string) => Promise<string>
  deleteConversation: (id: string) => Promise<void>
  renameConversation: (id: string, title: string) => Promise<void>
  pinConversation: (id: string, pinned: boolean) => Promise<void>
  duplicateConversation: (id: string) => Promise<void>

  sendMessage: (text: string, modelId?: string, skillId?: string, modeId?: string, webSearch?: boolean) => void
  stopGeneration: () => void
  rateMessage: (id: string, rating: number) => Promise<void>
}

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [],
  activeId: null,
  messages: [],
  isStreaming: false,
  streamingText: '',
  streamingThinking: '',
  streamMeta: null,
  lastUsage: null,
  abortController: null,
  reasoningSteps: [],
  skillProgress: [],
  activeMode: 'normal',
  searchStatus: null,
  searchSources: null,

  loadConversations: async () => {
    const { conversations } = await api.conversations.list()
    set({ conversations })
  },

  selectConversation: async (id: string) => {
    set({ activeId: id, messages: [], streamingText: '', streamingThinking: '', lastUsage: null })
    const { messages } = await api.conversations.get(id)
    set({ messages })
  },

  createConversation: async (title?: string) => {
    const conv = await api.conversations.create({ title: title || 'New conversation' })
    await get().loadConversations()
    set({ activeId: conv.id, messages: [] })
    return conv.id
  },

  deleteConversation: async (id: string) => {
    await api.conversations.delete(id)
    if (get().activeId === id) {
      set({ activeId: null, messages: [] })
    }
    await get().loadConversations()
  },

  renameConversation: async (id: string, title: string) => {
    await api.conversations.patch(id, { title })
    await get().loadConversations()
  },

  pinConversation: async (id: string, pinned: boolean) => {
    await api.conversations.patch(id, { pinned })
    await get().loadConversations()
  },

  duplicateConversation: async (id: string) => {
    await api.conversations.duplicate(id)
    await get().loadConversations()
  },

  sendMessage: (text: string, modelId = 'auto', skillId = 'normal', modeId = 'normal', webSearch = false) => {
    const { activeId, messages } = get()

    const userMsg: Message = {
      id: crypto.randomUUID(),
      conversation_id: activeId || '',
      role: 'user',
      content: text,
      content_raw: null,
      thinking_content: null,
      model: null,
      provider: null,
      tokens_in: 0,
      tokens_out: 0,
      tokens_thinking: 0,
      cost_usd: 0,
      latency_ms: null,
      first_token_ms: null,
      created_at: new Date().toISOString(),
      edited: false,
      stopped: false,
      rating: 0,
      version: 1,
      parent_message_id: null,
    }

    const history = [...messages, userMsg].map((m) => ({
      role: m.role,
      content: m.content,
    }))

    const abort = new AbortController()

    set({
      messages: [...messages, userMsg],
      isStreaming: true,
      streamingText: '',
      streamingThinking: '',
      streamMeta: null,
      lastUsage: null,
      abortController: abort,
      reasoningSteps: [],
      skillProgress: [],
      activeMode: modeId,
      searchStatus: null,
      searchSources: null,
    })

    streamChat(
      {
        message: text,
        conversation_id: activeId,
        model_id: modelId,
        skill_id: skillId,
        mode_id: modeId,
        messages: history,
        web_search: webSearch,
      },
      {
        onMeta: (meta) => set({ streamMeta: meta }),
        onThinking: (t) => set((s) => ({ streamingThinking: s.streamingThinking + t })),
        onSearch: (data) => {
          set({ searchStatus: data })
          if (data.status === 'done' && data.sources) {
            set({ searchSources: data.sources })
          }
        },
        onText: (t) => set((s) => ({ streamingText: s.streamingText + t })),
        onUsage: (usage) => set({ lastUsage: usage }),
        onReasoningStep: (data: ReasoningStepEvent) => set((s) => ({
          reasoningSteps: [...s.reasoningSteps, { ...data, timestamp: Date.now() }],
        })),
        onSkillProgress: (data: SkillProgressEvent) => set((s) => ({
          skillProgress: [...s.skillProgress, data],
        })),
        onError: (msg) => {
          set((s) => ({ streamingText: s.streamingText + `\n\n**Error:** ${msg}`, isStreaming: false }))
        },
        onDone: () => {
          const state = get()
          const assistantMsg: Message = {
            id: crypto.randomUUID(),
            conversation_id: activeId || '',
            role: 'assistant',
            content: state.streamingText,
            content_raw: null,
            thinking_content: state.streamingThinking || null,
            model: state.streamMeta?.model_key || null,
            provider: state.streamMeta?.provider || null,
            tokens_in: state.lastUsage?.tokens_in || 0,
            tokens_out: state.lastUsage?.tokens_out || 0,
            tokens_thinking: state.lastUsage?.tokens_thinking || 0,
            cost_usd: state.lastUsage?.cost_usd || 0,
            latency_ms: state.lastUsage?.latency_ms || null,
            first_token_ms: null,
            created_at: new Date().toISOString(),
            edited: false,
            stopped: false,
            rating: 0,
            version: 1,
            parent_message_id: null,
          }
          set((s) => ({
            messages: [...s.messages, assistantMsg],
            isStreaming: false,
            streamingText: '',
            streamingThinking: '',
            abortController: null,
          }))
          get().loadConversations()
        },
      },
      abort.signal,
    )
  },

  stopGeneration: () => {
    get().abortController?.abort()
    set({ isStreaming: false, abortController: null })
  },

  rateMessage: async (id: string, rating: number) => {
    await api.messages.rate(id, rating)
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, rating } : m)),
    }))
  },
}))
