import { Show } from 'solid-js'
import { PanelRight } from 'lucide-solid'
import { chatState } from '../../stores/chat'
import { uiState, toggleRightPanel } from '../../stores/ui'
import { formatCost, formatTokens, formatLatency } from '../../lib/cost'
import { AppNav } from './AppNav'

export function TopBar() {
  return (
    <div
      class="h-11 flex items-center px-3 gap-2 flex-shrink-0"
      style={{ 'border-bottom': '1px solid oklch(0.30 0.03 185)', background: 'oklch(0.22 0.025 185)' }}
      data-tauri-drag-region
    >
      <span
        class="text-sm mr-1 select-none"
        style={{ 'font-family': 'var(--font-display)', 'font-weight': '700', color: 'oklch(0.72 0.17 162)' }}
      >
        Emily
      </span>
      <div class="w-px h-5" style={{ background: 'oklch(0.30 0.03 185)' }} />
      <AppNav />

      <div class="flex-1" data-tauri-drag-region />

      <Show when={chatState.lastUsage || chatState.isStreaming}>
        <div
          class="flex items-center gap-3"
          style={{ 'font-size': 'var(--text-small)', 'font-family': 'var(--font-mono)', color: 'oklch(0.50 0.04 185)' }}
        >
          <Show when={chatState.lastUsage}>
            {(usage) => (
              <>
                <span>in: {formatTokens(usage().tokens_in)}</span>
                <span>out: {formatTokens(usage().tokens_out)}</span>
                <Show when={usage().tokens_thinking > 0}>
                  <span style={{ color: 'oklch(0.72 0.17 162)' }}>
                    think: {formatTokens(usage().tokens_thinking)}
                  </span>
                </Show>
                <span
                  style={{
                    color: usage().cost_usd > 0.05
                      ? 'oklch(0.75 0.16 85)'
                      : 'oklch(0.72 0.15 145)',
                  }}
                >
                  {formatCost(usage().cost_usd)}
                </span>
                <span>{formatLatency(usage().latency_ms)}</span>
              </>
            )}
          </Show>
          <Show when={chatState.isStreaming}>
            <span class="flex items-center gap-1" style={{ color: 'oklch(0.72 0.17 162)' }}>
              <span
                class="w-1.5 h-1.5 rounded-full animate-pulse"
                style={{ background: 'oklch(0.72 0.17 162)' }}
              />
              streaming
            </span>
          </Show>
        </div>
      </Show>

      <button
        onClick={toggleRightPanel}
        class="p-1.5 rounded-lg transition-colors"
        style={{ color: uiState.rightPanelVisible ? 'oklch(0.72 0.17 162)' : 'oklch(0.50 0.04 185)' }}
        title="Toggle reasoning panel"
      >
        <PanelRight size={16} />
      </button>
    </div>
  )
}
