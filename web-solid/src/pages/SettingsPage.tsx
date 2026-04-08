import { createSignal, lazy, Switch, Match, type JSX } from 'solid-js'
import { User, Sparkles, Shield, Volume2, Wrench } from 'lucide-solid'
import type { LucideIcon } from 'lucide-solid'

const ProfileSettings = lazy(() => import('./settings/ProfileSettings'))
const PersonaSettings = lazy(() => import('./settings/PersonaSettings'))
const PermissionsSettings = lazy(() => import('./settings/PermissionsSettings'))
const AudioSettings = lazy(() => import('./settings/AudioSettings'))
const AdvancedSettings = lazy(() => import('./settings/AdvancedSettings'))

type SettingsTab = 'profile' | 'persona' | 'permissions' | 'audio' | 'advanced'

const TABS: Array<{ id: SettingsTab; label: string; icon: LucideIcon }> = [
  { id: 'profile',     label: 'Profile',     icon: User },
  { id: 'persona',     label: 'Persona',     icon: Sparkles },
  { id: 'permissions', label: 'Permissions', icon: Shield },
  { id: 'audio',       label: 'Audio',       icon: Volume2 },
  { id: 'advanced',    label: 'Advanced',    icon: Wrench },
]

export function SettingsPage() {
  const [activeTab, setActiveTab] = createSignal<SettingsTab>('profile')

  return (
    <div class="flex flex-1 min-h-0" style={{ background: 'oklch(0.18 0.02 185)' }}>
      {/* Tab navigation — left sidebar */}
      <nav
        class="shrink-0 flex flex-col gap-1 p-3 overflow-y-auto border-r"
        style={{
          width: '200px',
          'border-color': 'oklch(0.30 0.02 185)',
          background: 'oklch(0.16 0.02 185)',
        }}
      >
        {TABS.map((tab) => {
          const Icon = tab.icon
          return (
            <button
              onClick={() => setActiveTab(tab.id)}
              class="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors text-left"
              style={{
                background: activeTab() === tab.id ? 'oklch(0.25 0.04 162 / 0.3)' : 'transparent',
                color: activeTab() === tab.id ? 'oklch(0.72 0.17 162)' : 'oklch(0.55 0.03 185)',
              }}
            >
              <Icon size={16} />
              {tab.label}
            </button>
          )
        })}
      </nav>

      {/* Content area */}
      <div class="flex-1 overflow-y-auto p-6">
        <div class="max-w-lg mx-auto">
          <Switch fallback={
            <div
              class="flex items-center justify-center h-32 text-sm"
              style={{ color: 'oklch(0.50 0.03 185)' }}
            >
              Select a settings tab
            </div>
          }>
            <Match when={activeTab() === 'profile'}>
              <ProfileSettings />
            </Match>
            <Match when={activeTab() === 'persona'}>
              <PersonaSettings />
            </Match>
            <Match when={activeTab() === 'permissions'}>
              <PermissionsSettings />
            </Match>
            <Match when={activeTab() === 'audio'}>
              <AudioSettings />
            </Match>
            <Match when={activeTab() === 'advanced'}>
              <AdvancedSettings />
            </Match>
          </Switch>
        </div>
      </div>
    </div>
  )
}
