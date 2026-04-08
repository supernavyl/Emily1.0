import { ErrorBoundary as SolidErrorBoundary, type JSX } from 'solid-js'
import { AlertTriangle, RefreshCw } from 'lucide-solid'

interface Props {
  children: JSX.Element
}

export function ErrorBoundary(props: Props) {
  return (
    <SolidErrorBoundary
      fallback={(err: Error, reset) => (
        <div class="flex items-center justify-center h-full" style={{ background: 'oklch(0.18 0.02 185)' }}>
          <div class="text-center space-y-4 max-w-md p-8">
            <AlertTriangle size={48} style={{ color: 'oklch(0.75 0.16 85)', margin: '0 auto' }} />
            <h2 class="text-lg font-semibold" style={{ color: 'oklch(0.93 0.01 90)' }}>
              Something went wrong
            </h2>
            <p class="text-sm" style={{ color: 'oklch(0.65 0.03 185)' }}>
              {err.message}
            </p>
            <button
              onClick={() => {
                reset()
                window.location.reload()
              }}
              class="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-colors"
              style={{ background: 'oklch(0.72 0.17 162)', color: 'oklch(0.18 0.02 185)' }}
            >
              <RefreshCw size={16} />
              Reload
            </button>
          </div>
        </div>
      )}
    >
      {props.children}
    </SolidErrorBoundary>
  )
}
