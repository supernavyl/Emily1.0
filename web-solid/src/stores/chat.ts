import { createStore, produce } from 'solid-js/store'
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

  // Reasoning state
  reasoningSteps: ReasoningStep[]
  skillProgress: SkillProgressEvent[]
  activeMode: string

  // Web search state
  searchStatus: SearchEvent | null
  searchSources: Array<{ title: string; url: string }> | null
}

// Module-level abort controller (not serializable — kept outside store)
let abortController: AbortController | null = null

const [chatState, setChatState] = createStore<ChatState>({
  conversations: [],
  activeId: null,
  messages: [],
  isStreaming: false,
  streamingText: '',
  streamingThinking: '',
  streamMeta: null,
  lastUsage: null,
  reasoningSteps: [],
  skillProgress: [],
  activeMode: 'normal',
  searchStatus: null,
  searchSources: null,
})

export { chatState }

export async function loadConversations(): Promise<void> {
  const { conversations } = await api.conversations.list()
  setChatState('conversations', conversations)
}

export async function selectConversation(id: string): Promise<void> {
  setChatState({
    activeId: id,
    messages: [],
    streamingText: '',
    streamingThinking: '',
    lastUsage: null,
  })
  const { messages } = await api.conversations.get(id)
  setChatState('messages', messages)
}

export async function createConversation(title?: string): Promise<string> {
  const conv = await api.conversations.create({ title: title ?? 'New conversation' })
  await loadConversations()
  setChatState({ activeId: conv.id, messages: [] })
  return conv.id
}

export async function deleteConversation(id: string): Promise<void> {
  await api.conversations.delete(id)
  if (chatState.activeId === id) {
    setChatState({ activeId: null, messages: [] })
  }
  await loadConversations()
}

export async function renameConversation(id: string, title: string): Promise<void> {
  await api.conversations.patch(id, { title })
  await loadConversations()
}

export async function pinConversation(id: string, pinned: boolean): Promise<void> {
  await api.conversations.patch(id, { pinned })
  await loadConversations()
}

export async function duplicateConversation(id: string): Promise<void> {
  await api.conversations.duplicate(id)
  await loadConversations()
}

export function sendMessage(
  text: string,
  modelId = 'auto',
  skillId = 'normal',
  modeId = 'normal',
  webSearch = false,
): void {
  const activeId = chatState.activeId

  const userMsg: Message = {
    id: crypto.randomUUID(),
    conversation_id: activeId ?? '',
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

  const history = [...chatState.messages, userMsg].map((m) => ({
    role: m.role,
    content: m.content,
  }))

  const abort = new AbortController()
  abortController = abort

  setChatState(produce((s) => {
    s.messages.push(userMsg)
    s.isStreaming = true
    s.streamingText = ''
    s.streamingThinking = ''
    s.streamMeta = null
    s.lastUsage = null
    s.reasoningSteps = []
    s.skillProgress = []
    s.activeMode = modeId
    s.searchStatus = null
    s.searchSources = null
  }))

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
      onMeta: (meta) => setChatState('streamMeta', meta),
      onThinking: (t) => setChatState('streamingThinking', (prev) => prev + t),
      onSearch: (data) => {
        setChatState('searchStatus', data)
        if (data.status === 'done' && data.sources) {
          setChatState('searchSources', data.sources)
        }
      },
      onText: (t) => setChatState('streamingText', (prev) => prev + t),
      onUsage: (usage) => setChatState('lastUsage', usage),
      onReasoningStep: (data: ReasoningStepEvent) =>
        setChatState('reasoningSteps', produce((steps) => {
          steps.push({ ...data, timestamp: Date.now() })
        })),
      onSkillProgress: (data: SkillProgressEvent) =>
        setChatState('skillProgress', produce((progress) => {
          progress.push(data)
        })),
      onError: (msg) => {
        setChatState('streamingText', (prev) => prev + `\n\n**Error:** ${msg}`)
        setChatState('isStreaming', false)
      },
      onDone: () => {
        const assistantMsg: Message = {
          id: crypto.randomUUID(),
          conversation_id: activeId ?? '',
          role: 'assistant',
          content: chatState.streamingText,
          content_raw: null,
          thinking_content: chatState.streamingThinking || null,
          model: chatState.streamMeta?.model_key ?? null,
          provider: chatState.streamMeta?.provider ?? null,
          tokens_in: chatState.lastUsage?.tokens_in ?? 0,
          tokens_out: chatState.lastUsage?.tokens_out ?? 0,
          tokens_thinking: chatState.lastUsage?.tokens_thinking ?? 0,
          cost_usd: chatState.lastUsage?.cost_usd ?? 0,
          latency_ms: chatState.lastUsage?.latency_ms ?? null,
          first_token_ms: null,
          created_at: new Date().toISOString(),
          edited: false,
          stopped: false,
          rating: 0,
          version: 1,
          parent_message_id: null,
        }
        setChatState(produce((s) => {
          s.messages.push(assistantMsg)
          s.isStreaming = false
          s.streamingText = ''
          s.streamingThinking = ''
        }))
        abortController = null
        void loadConversations()
      },
    },
    abort.signal,
  )
}

export function stopGeneration(): void {
  abortController?.abort()
  abortController = null
  setChatState('isStreaming', false)
}

export async function rateMessage(id: string, rating: number): Promise<void> {
  await api.messages.rate(id, rating)
  setChatState('messages', (m) => m.id === id, 'rating', rating)
}
