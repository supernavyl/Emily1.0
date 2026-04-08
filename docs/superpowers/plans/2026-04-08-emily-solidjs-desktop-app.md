# Emily SolidJS Desktop App — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild Emily's desktop frontend from React 19 to SolidJS in a new `web-solid/` directory, reusing the Tauri 2 Rust shell and framework-free TypeScript layers verbatim.

**Architecture:** SolidJS signals + `createStore`/`produce()` for fine-grained reactivity. No virtual DOM. Ring buffer for brain events, rAF batching for WebSocket, virtualized `<For>` for EventStream. Unified/remark/rehype markdown pipeline with Shiki code blocks. Signal-based routing (no router library).

**Tech Stack:** SolidJS, TypeScript 5.9, Vite 7, Tailwind 4, Tauri 2, `@tanstack/solid-virtual`, Shiki, unified/remark/rehype, DOMPurify, lucide-solid

**Spec:** `docs/superpowers/specs/2026-04-08-emily-solidjs-desktop-app-design.md`

**Kill switch:** Day 5 — chat SSE + brain WS must work or abandon.

---

## File Structure

```
~/Emily1.0/web-solid/
├── src/
│   ├── api/                    # COPIED verbatim from web/src/api/
│   │   ├── client.ts           # Typed fetch wrapper (89 LOC)
│   │   ├── types.ts            # 15 TS interfaces (148 LOC)
│   │   └── sse.ts              # SSE stream reader (152 LOC)
│   ├── lib/                    # COPIED then adapted
│   │   ├── env.ts              # Tauri detection (40 LOC, verbatim)
│   │   ├── cost.ts             # Cost formatting (23 LOC, verbatim)
│   │   ├── time.ts             # Time formatting (33 LOC, verbatim)
│   │   ├── mode-themes.ts      # ADAPTED: lucide-react → lucide-solid
│   │   └── skill-icons.ts      # ADAPTED: lucide-react → lucide-solid
│   ├── stores/                 # REWRITTEN: Zustand → SolidJS createStore
│   │   ├── chat.ts             # Chat state + SSE streaming
│   │   ├── brain.ts            # Brain events + ring buffer + polling
│   │   ├── ui.ts               # UI state (page, theme, panels)
│   │   ├── models.ts           # Models, skills, modes
│   │   └── onboarding.ts       # Onboarding phases
│   ├── primitives/             # REWRITTEN: React hooks → SolidJS
│   │   ├── createBrainWS.ts    # Brain WebSocket + rAF batching
│   │   ├── createKeyboard.ts   # Global keyboard shortcuts
│   │   ├── createPolling.ts    # Generic polling primitive
│   │   └── createModeAccent.ts # CSS custom property sync
│   ├── components/
│   │   ├── layout/
│   │   │   ├── MainLayout.tsx  # App shell with page routing
│   │   │   ├── Sidebar.tsx     # Conversation list (chat page)
│   │   │   ├── TopBar.tsx      # Header + nav + model selector
│   │   │   └── AppNav.tsx      # Tab navigation
│   │   ├── chat/
│   │   │   ├── MessageList.tsx  # Scrollable message feed
│   │   │   ├── InputPanel.tsx   # Message input + attachments
│   │   │   ├── EmilyMessage.tsx # Emily response bubble
│   │   │   ├── UserMessage.tsx  # User message bubble
│   │   │   ├── ModeSelector.tsx # Mode/skill picker overlay
│   │   │   └── EmptyState.tsx   # Landing page
│   │   ├── brain/
│   │   │   ├── BrainTabs.tsx    # Tab bar (8 sections)
│   │   │   ├── NeuralOverview.tsx # FSM + resource rings
│   │   │   ├── EmotionalCortex.tsx
│   │   │   ├── CognitiveProcesses.tsx
│   │   │   ├── MemoryArchitecture.tsx
│   │   │   ├── ModelFleet.tsx
│   │   │   ├── PersonalityMatrix.tsx
│   │   │   ├── EventStream.tsx  # Virtualized event list
│   │   │   └── BrainChat.tsx    # Inline query terminal
│   │   ├── charts/
│   │   │   ├── ProgressRing.tsx
│   │   │   ├── RadarChart.tsx
│   │   │   ├── Sparkline.tsx
│   │   │   ├── DonutChart.tsx
│   │   │   └── BarChart.tsx
│   │   ├── markdown/
│   │   │   ├── MarkdownRenderer.tsx  # unified pipeline
│   │   │   └── CodeBlock.tsx         # Shiki async highlight
│   │   ├── reasoning/
│   │   │   ├── ReasoningPanelV2.tsx
│   │   │   ├── FlowDiagram.tsx
│   │   │   ├── ThinkingPhases.tsx
│   │   │   ├── ReasoningTimeline.tsx
│   │   │   ├── ModelComparison.tsx
│   │   │   ├── MemoryInsight.tsx
│   │   │   └── ReasoningMetrics.tsx
│   │   ├── search/
│   │   │   └── SearchOverlay.tsx
│   │   ├── auth/
│   │   │   ├── LoginScreen.tsx
│   │   │   └── OnboardingFlow.tsx
│   │   └── common/
│   │       └── ErrorBoundary.tsx
│   ├── pages/
│   │   ├── BrainPage.tsx
│   │   ├── SettingsPage.tsx
│   │   ├── settings/
│   │   │   ├── ProfileSettings.tsx
│   │   │   ├── PersonaSettings.tsx
│   │   │   ├── PermissionsSettings.tsx
│   │   │   ├── AudioSettings.tsx
│   │   │   └── AdvancedSettings.tsx
│   │   ├── VoicePage.tsx
│   │   ├── LogsPage.tsx
│   │   ├── VisionPage.tsx
│   │   └── TerminalPage.tsx
│   ├── App.tsx
│   ├── main.tsx
│   └── index.css
├── src-tauri/          # Symlink to ../web/src-tauri/
├── index.html
├── vite.config.ts
├── tsconfig.json
├── tsconfig.app.json
├── eslint.config.js
└── package.json
```

---

## Phase 0: Scaffold + Infrastructure

### Task 1: Project Scaffold

**Files:**
- Create: `web-solid/package.json`
- Create: `web-solid/vite.config.ts`
- Create: `web-solid/tsconfig.json`
- Create: `web-solid/tsconfig.app.json`
- Create: `web-solid/eslint.config.js`
- Create: `web-solid/index.html`
- Create: `web-solid/src/main.tsx`
- Create: `web-solid/src/App.tsx` (minimal placeholder)
- Create: `web-solid/src/index.css`

- [ ] **Step 1: Create project directory**

```bash
mkdir -p ~/Emily1.0/web-solid/src
```

- [ ] **Step 2: Create package.json**

```json
{
  "name": "emily-desktop-solid",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest",
    "lint": "eslint src/",
    "tauri": "tauri"
  },
  "dependencies": {
    "solid-js": "^1.9.0",
    "@tauri-apps/api": "^2.0.0",
    "@tauri-apps/plugin-dialog": "^2.0.0",
    "@tauri-apps/plugin-notification": "^2.0.0",
    "@tauri-apps/plugin-log": "^2.0.0",
    "@tanstack/solid-virtual": "^3.11.0",
    "lucide-solid": "^0.468.0",
    "unified": "^11.0.0",
    "remark-parse": "^11.0.0",
    "remark-gfm": "^4.0.0",
    "remark-rehype": "^11.0.0",
    "rehype-stringify": "^10.0.0",
    "dompurify": "^3.2.0",
    "shiki": "^1.24.0"
  },
  "devDependencies": {
    "@tauri-apps/cli": "^2.0.0",
    "typescript": "~5.9.0",
    "vite": "^7.0.0",
    "vite-plugin-solid": "^2.11.0",
    "@tailwindcss/vite": "^4.0.0",
    "tailwindcss": "^4.0.0",
    "eslint": "^9.0.0",
    "eslint-plugin-solid": "^0.14.0",
    "vitest": "^3.0.0",
    "@solidjs/testing-library": "^0.8.0",
    "jsdom": "^25.0.0",
    "@types/dompurify": "^3.0.0"
  }
}
```

- [ ] **Step 3: Create vite.config.ts**

```typescript
/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import solid from 'vite-plugin-solid'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [solid(), tailwindcss()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
  server: {
    host: '127.0.0.1',
    port: 1421,
    strictPort: true,
    proxy: {
      '/api/v1': {
        target: 'http://127.0.0.1:8001',
      },
      '/api': {
        target: 'http://127.0.0.1:8001',
        rewrite: (path: string) => path.replace(/^\/api/, ''),
      },
      '/ws': {
        target: 'ws://127.0.0.1:8001',
        ws: true,
      },
    },
  },
})
```

Note: Port 1421 to avoid collision with React app on 1420.

- [ ] **Step 4: Create tsconfig.json**

```json
{
  "files": [],
  "references": [
    { "path": "./tsconfig.app.json" }
  ]
}
```

- [ ] **Step 5: Create tsconfig.app.json**

```json
{
  "compilerOptions": {
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.app.tsbuildinfo",
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "types": ["vite/client"],
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "verbatimModuleSyntax": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "preserve",
    "jsxImportSource": "solid-js",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "erasableSyntaxOnly": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedSideEffectImports": true
  },
  "include": ["src"]
}
```

- [ ] **Step 6: Create eslint.config.js**

```javascript
import solid from 'eslint-plugin-solid/configs/recommended.js'

export default [
  solid,
  {
    files: ['src/**/*.{ts,tsx}'],
    rules: {
      'solid/reactivity': 'error',
      'solid/no-destructure': 'error',
      'solid/jsx-no-undef': 'error',
    },
  },
]
```

- [ ] **Step 7: Create index.html**

```html
<!doctype html>
<html lang="en" class="dark">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Emily</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Syne:wght@400..800&family=Literata:ital,opsz,wght@0,7..72,200..900;1,7..72,200..900&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 8: Create minimal main.tsx**

```typescript
/* @refresh reload */
import { render } from 'solid-js/web'
import App from './App'
import './index.css'

const root = document.getElementById('root')

// SAFETY: root element is guaranteed by index.html
render(() => <App />, root!)
```

- [ ] **Step 9: Create minimal App.tsx placeholder**

```typescript
import type { Component } from 'solid-js'

const App: Component = () => {
  return (
    <div class="flex h-screen w-screen items-center justify-center bg-surface text-text-primary">
      <h1 class="font-display text-2xl">Emily — SolidJS</h1>
    </div>
  )
}

export default App
```

- [ ] **Step 10: Create test setup**

```bash
mkdir -p ~/Emily1.0/web-solid/src/test
```

Create `web-solid/src/test/setup.ts`:

```typescript
import '@solidjs/testing-library/cleanup'
```

- [ ] **Step 11: Symlink src-tauri**

```bash
cd ~/Emily1.0/web-solid && ln -s ../web/src-tauri src-tauri
```

- [ ] **Step 12: Install dependencies**

```bash
cd ~/Emily1.0/web-solid && npm install
```

- [ ] **Step 13: Verify dev server starts**

```bash
cd ~/Emily1.0/web-solid && npx vite --port 1421 &
# Wait 3 seconds, then curl localhost:1421 to verify it serves HTML
# Kill the dev server
```

- [ ] **Step 14: Commit scaffold**

```bash
cd ~/Emily1.0 && git add web-solid/
git commit -m "feat(web-solid): scaffold SolidJS + Vite + Tailwind + Tauri project"
```

---

### Task 2: Copy Verbatim Files + Adapt Icon Files

**Files:**
- Copy: `web-solid/src/api/client.ts` (from `web/src/api/client.ts`)
- Copy: `web-solid/src/api/types.ts` (from `web/src/api/types.ts`)
- Copy: `web-solid/src/api/sse.ts` (from `web/src/api/sse.ts`)
- Copy: `web-solid/src/lib/env.ts` (from `web/src/lib/env.ts`)
- Copy: `web-solid/src/lib/cost.ts` (from `web/src/lib/cost.ts`)
- Copy: `web-solid/src/lib/time.ts` (from `web/src/lib/time.ts`)
- Copy: `web-solid/src/index.css` (from `web/src/index.css`)
- Create: `web-solid/src/lib/mode-themes.ts` (adapted — `lucide-react` → `lucide-solid`)
- Create: `web-solid/src/lib/skill-icons.ts` (adapted — `lucide-react` → `lucide-solid`)

- [ ] **Step 1: Copy framework-free API and lib files**

```bash
mkdir -p ~/Emily1.0/web-solid/src/{api,lib}
cp ~/Emily1.0/web/src/api/client.ts ~/Emily1.0/web-solid/src/api/client.ts
cp ~/Emily1.0/web/src/api/types.ts ~/Emily1.0/web-solid/src/api/types.ts
cp ~/Emily1.0/web/src/api/sse.ts ~/Emily1.0/web-solid/src/api/sse.ts
cp ~/Emily1.0/web/src/lib/env.ts ~/Emily1.0/web-solid/src/lib/env.ts
cp ~/Emily1.0/web/src/lib/cost.ts ~/Emily1.0/web-solid/src/lib/cost.ts
cp ~/Emily1.0/web/src/lib/time.ts ~/Emily1.0/web-solid/src/lib/time.ts
```

- [ ] **Step 2: Copy index.css**

```bash
cp ~/Emily1.0/web/src/index.css ~/Emily1.0/web-solid/src/index.css
```

This CSS is framework-agnostic (Tailwind 4 + custom properties + keyframes). Works identically in SolidJS.

- [ ] **Step 3: Create mode-themes.ts (adapted for lucide-solid)**

Replace `lucide-react` → `lucide-solid` and `LucideIcon` → `IconNode`. The data is identical.

```typescript
import type { IconNode } from 'lucide-solid'
import {
  MessageSquare, Brain, Code2, FlaskConical, BarChart3, TrendingUp,
  PenLine, Lightbulb, Music, Clapperboard,
  Megaphone, Share2,
  Mic, Zap, GraduationCap, Swords, Sparkles,
  Languages, GitCompareArrows,
} from 'lucide-solid'

export type ModeCategory = 'thinking' | 'creative' | 'professional' | 'communication' | 'utility'

export interface ModeTheme {
  id: string
  name: string
  description: string
  gradient: string
  gradientStops: [string, string]
  glow: string
  accent: string
  icon: IconNode
  category: ModeCategory
  capabilities: ('thinking' | 'web_search' | 'code_exec' | 'multi_model')[]
  temperature: number
}

const themes: ModeTheme[] = [
  {
    id: 'normal',
    name: 'Normal',
    description: 'Balanced, general-purpose assistant',
    gradient: 'linear-gradient(135deg, oklch(0.72 0.17 162), oklch(0.65 0.12 185))',
    gradientStops: ['oklch(0.72 0.17 162)', 'oklch(0.65 0.12 185)'],
    glow: 'oklch(0.72 0.17 162 / 0.35)',
    accent: 'oklch(0.72 0.17 162)',
    icon: MessageSquare,
    category: 'communication',
    capabilities: [],
    temperature: 0.7,
  },
  {
    id: 'deep_think',
    name: 'Deep Think',
    description: 'Extended reasoning and step-by-step analysis',
    gradient: 'linear-gradient(135deg, oklch(0.60 0.15 230), oklch(0.65 0.12 185), oklch(0.55 0.14 220))',
    gradientStops: ['oklch(0.60 0.15 230)', 'oklch(0.55 0.14 220)'],
    glow: 'oklch(0.60 0.15 230 / 0.35)',
    accent: 'oklch(0.60 0.15 230)',
    icon: Brain,
    category: 'thinking',
    capabilities: ['thinking'],
    temperature: 0.3,
  },
  {
    id: 'code',
    name: 'Code',
    description: 'Programming, debugging, and technical implementation',
    gradient: 'linear-gradient(135deg, oklch(0.72 0.17 162), oklch(0.65 0.12 185))',
    gradientStops: ['oklch(0.72 0.17 162)', 'oklch(0.65 0.12 185)'],
    glow: 'oklch(0.72 0.17 162 / 0.35)',
    accent: 'oklch(0.72 0.17 162)',
    icon: Code2,
    category: 'thinking',
    capabilities: ['thinking', 'code_exec'],
    temperature: 0.2,
  },
  {
    id: 'research',
    name: 'Research',
    description: 'Deep investigation with sources and citations',
    gradient: 'linear-gradient(135deg, oklch(0.60 0.15 230), oklch(0.65 0.12 185))',
    gradientStops: ['oklch(0.60 0.15 230)', 'oklch(0.65 0.12 185)'],
    glow: 'oklch(0.60 0.15 230 / 0.35)',
    accent: 'oklch(0.60 0.15 230)',
    icon: FlaskConical,
    category: 'thinking',
    capabilities: ['thinking', 'web_search'],
    temperature: 0.4,
  },
  {
    id: 'analyst',
    name: 'Analyst',
    description: 'Data analysis, metrics, and quantitative reasoning',
    gradient: 'linear-gradient(135deg, oklch(0.70 0.13 215), oklch(0.60 0.15 230))',
    gradientStops: ['oklch(0.70 0.13 215)', 'oklch(0.60 0.15 230)'],
    glow: 'oklch(0.70 0.13 215 / 0.35)',
    accent: 'oklch(0.70 0.13 215)',
    icon: BarChart3,
    category: 'thinking',
    capabilities: ['thinking', 'code_exec'],
    temperature: 0.3,
  },
  {
    id: 'market_research',
    name: 'Market Research',
    description: 'Market trends, competitor analysis, and industry insights',
    gradient: 'linear-gradient(135deg, oklch(0.72 0.15 185), oklch(0.65 0.12 200))',
    gradientStops: ['oklch(0.72 0.15 185)', 'oklch(0.65 0.12 200)'],
    glow: 'oklch(0.72 0.15 185 / 0.35)',
    accent: 'oklch(0.72 0.15 185)',
    icon: TrendingUp,
    category: 'thinking',
    capabilities: ['thinking', 'web_search'],
    temperature: 0.4,
  },
  {
    id: 'writing',
    name: 'Writing',
    description: 'Creative and professional writing, editing, prose',
    gradient: 'linear-gradient(135deg, oklch(0.65 0.22 15), oklch(0.65 0.20 350))',
    gradientStops: ['oklch(0.65 0.22 15)', 'oklch(0.65 0.20 350)'],
    glow: 'oklch(0.65 0.22 15 / 0.35)',
    accent: 'oklch(0.65 0.22 15)',
    icon: PenLine,
    category: 'creative',
    capabilities: [],
    temperature: 0.8,
  },
  {
    id: 'brainstorm',
    name: 'Brainstorm',
    description: 'Divergent thinking, idea generation, creative exploration',
    gradient: 'linear-gradient(135deg, oklch(0.75 0.16 85), oklch(0.78 0.18 75))',
    gradientStops: ['oklch(0.75 0.16 85)', 'oklch(0.78 0.18 75)'],
    glow: 'oklch(0.75 0.16 85 / 0.35)',
    accent: 'oklch(0.75 0.16 85)',
    icon: Lightbulb,
    category: 'creative',
    capabilities: ['thinking'],
    temperature: 0.9,
  },
  {
    id: 'singing',
    name: 'Singing',
    description: 'Songwriting, lyrics, melody composition',
    gradient: 'linear-gradient(135deg, oklch(0.72 0.17 162), oklch(0.65 0.20 350))',
    gradientStops: ['oklch(0.72 0.17 162)', 'oklch(0.65 0.20 350)'],
    glow: 'oklch(0.72 0.17 162 / 0.35)',
    accent: 'oklch(0.72 0.17 162)',
    icon: Music,
    category: 'creative',
    capabilities: [],
    temperature: 0.85,
  },
  {
    id: 'video_script',
    name: 'Video Script',
    description: 'Screenwriting, video scripts, storyboarding',
    gradient: 'linear-gradient(135deg, oklch(0.70 0.19 45), oklch(0.65 0.20 25))',
    gradientStops: ['oklch(0.70 0.19 45)', 'oklch(0.65 0.20 25)'],
    glow: 'oklch(0.70 0.19 45 / 0.35)',
    accent: 'oklch(0.70 0.19 45)',
    icon: Clapperboard,
    category: 'creative',
    capabilities: [],
    temperature: 0.8,
  },
  {
    id: 'ad_copywriter',
    name: 'Ad Copywriter',
    description: 'Persuasive copy, headlines, marketing content',
    gradient: 'linear-gradient(135deg, oklch(0.65 0.20 350), oklch(0.65 0.22 15))',
    gradientStops: ['oklch(0.65 0.20 350)', 'oklch(0.65 0.22 15)'],
    glow: 'oklch(0.65 0.20 350 / 0.35)',
    accent: 'oklch(0.65 0.20 350)',
    icon: Megaphone,
    category: 'professional',
    capabilities: [],
    temperature: 0.75,
  },
  {
    id: 'social_media',
    name: 'Social Media',
    description: 'Platform-specific content, engagement strategy',
    gradient: 'linear-gradient(135deg, oklch(0.68 0.18 340), oklch(0.65 0.22 15))',
    gradientStops: ['oklch(0.68 0.18 340)', 'oklch(0.65 0.22 15)'],
    glow: 'oklch(0.68 0.18 340 / 0.35)',
    accent: 'oklch(0.68 0.18 340)',
    icon: Share2,
    category: 'professional',
    capabilities: ['web_search'],
    temperature: 0.75,
  },
  {
    id: 'voice',
    name: 'Voice',
    description: 'Conversational, speech-optimized responses',
    gradient: 'linear-gradient(135deg, oklch(0.73 0.18 55), oklch(0.70 0.19 45))',
    gradientStops: ['oklch(0.73 0.18 55)', 'oklch(0.70 0.19 45)'],
    glow: 'oklch(0.73 0.18 55 / 0.35)',
    accent: 'oklch(0.73 0.18 55)',
    icon: Mic,
    category: 'communication',
    capabilities: [],
    temperature: 0.7,
  },
  {
    id: 'concise',
    name: 'Concise',
    description: 'Short, direct answers without fluff',
    gradient: 'linear-gradient(135deg, oklch(0.65 0.12 185), oklch(0.68 0.14 200))',
    gradientStops: ['oklch(0.65 0.12 185)', 'oklch(0.68 0.14 200)'],
    glow: 'oklch(0.65 0.12 185 / 0.35)',
    accent: 'oklch(0.65 0.12 185)',
    icon: Zap,
    category: 'communication',
    capabilities: [],
    temperature: 0.5,
  },
  {
    id: 'tutor',
    name: 'Tutor',
    description: 'Patient teaching, explanations, guided learning',
    gradient: 'linear-gradient(135deg, oklch(0.72 0.15 145), oklch(0.65 0.12 185))',
    gradientStops: ['oklch(0.72 0.15 145)', 'oklch(0.65 0.12 185)'],
    glow: 'oklch(0.72 0.15 145 / 0.35)',
    accent: 'oklch(0.72 0.15 145)',
    icon: GraduationCap,
    category: 'communication',
    capabilities: ['thinking'],
    temperature: 0.6,
  },
  {
    id: 'debate',
    name: 'Debate',
    description: "Devil's advocate, counterarguments, critical analysis",
    gradient: 'linear-gradient(135deg, oklch(0.65 0.20 25), oklch(0.60 0.22 20))',
    gradientStops: ['oklch(0.65 0.20 25)', 'oklch(0.60 0.22 20)'],
    glow: 'oklch(0.65 0.20 25 / 0.35)',
    accent: 'oklch(0.65 0.20 25)',
    icon: Swords,
    category: 'communication',
    capabilities: ['thinking'],
    temperature: 0.7,
  },
  {
    id: 'eli5',
    name: 'ELI5',
    description: "Explain like I'm five — simple, fun, visual",
    gradient: 'linear-gradient(135deg, oklch(0.78 0.14 162), oklch(0.72 0.17 162))',
    gradientStops: ['oklch(0.78 0.14 162)', 'oklch(0.72 0.17 162)'],
    glow: 'oklch(0.78 0.14 162 / 0.35)',
    accent: 'oklch(0.78 0.14 162)',
    icon: Sparkles,
    category: 'communication',
    capabilities: [],
    temperature: 0.8,
  },
  {
    id: 'translate',
    name: 'Translate',
    description: 'Multi-language translation and localization',
    gradient: 'linear-gradient(135deg, oklch(0.68 0.14 200), oklch(0.65 0.12 185))',
    gradientStops: ['oklch(0.68 0.14 200)', 'oklch(0.65 0.12 185)'],
    glow: 'oklch(0.68 0.14 200 / 0.35)',
    accent: 'oklch(0.68 0.14 200)',
    icon: Languages,
    category: 'utility',
    capabilities: [],
    temperature: 0.3,
  },
  {
    id: 'compare',
    name: 'Compare',
    description: 'Side-by-side comparisons, pros and cons',
    gradient: 'linear-gradient(135deg, oklch(0.65 0.12 185), oklch(0.60 0.15 185))',
    gradientStops: ['oklch(0.65 0.12 185)', 'oklch(0.60 0.15 185)'],
    glow: 'oklch(0.65 0.12 185 / 0.35)',
    accent: 'oklch(0.65 0.12 185)',
    icon: GitCompareArrows,
    category: 'utility',
    capabilities: ['thinking'],
    temperature: 0.5,
  },
]

export const MODE_THEMES: Record<string, ModeTheme> = Object.fromEntries(
  themes.map((t) => [t.id, t])
)

export function getModeTheme(id: string): ModeTheme {
  return MODE_THEMES[id] ?? MODE_THEMES['normal']
}

export const CATEGORY_LABELS: Record<ModeCategory, string> = {
  thinking: 'Thinking & Analysis',
  creative: 'Creative',
  professional: 'Professional',
  communication: 'Communication',
  utility: 'Utility',
}

export const CATEGORY_ORDER: ModeCategory[] = [
  'thinking', 'creative', 'professional', 'communication', 'utility',
]

export function getModesByCategory(): Array<{ category: ModeCategory; label: string; modes: ModeTheme[] }> {
  return CATEGORY_ORDER.map((cat) => ({
    category: cat,
    label: CATEGORY_LABELS[cat],
    modes: themes.filter((t) => t.category === cat),
  }))
}
```

**Critical:** lucide-solid exports component functions, not `LucideIcon` type. The icon type is `IconNode` from `lucide-solid`. Verify the exact type name after install — it may be `Component` or the icons themselves may be typed differently. Check `node_modules/lucide-solid` after install.

- [ ] **Step 4: Create skill-icons.ts (adapted)**

```typescript
import {
  Languages, Code2, Music, FlaskConical, PenLine,
  Lightbulb, Brain, Zap, MessageSquare,
  Mic, BarChart3, GraduationCap, Swords, Sparkles,
  GitCompareArrows, Megaphone, Share2, Clapperboard, TrendingUp,
} from 'lucide-solid'
import type { IconNode } from 'lucide-solid'

const SKILL_ICON_MAP: Record<string, IconNode> = {
  translate:       Languages,
  code:            Code2,
  singing:         Music,
  research:        FlaskConical,
  writing:         PenLine,
  brainstorm:      Lightbulb,
  deep_think:      Brain,
  normal:          MessageSquare,
  voice:           Mic,
  concise:         Zap,
  analyst:         BarChart3,
  tutor:           GraduationCap,
  debate:          Swords,
  eli5:            Sparkles,
  compare:         GitCompareArrows,
  ad_copywriter:   Megaphone,
  social_media:    Share2,
  video_script:    Clapperboard,
  market_research: TrendingUp,
}

export function getSkillIcon(id: string): IconNode {
  return SKILL_ICON_MAP[id] ?? Zap
}
```

**Note:** lucide-solid icon types may differ from lucide-react. After npm install, verify the actual exported type by checking `node_modules/lucide-solid/dist/types.d.ts`. If `IconNode` doesn't exist, use `typeof MessageSquare` or `Component<{ class?: string }>` as the type.

- [ ] **Step 5: Verify TypeScript compilation of copied files**

```bash
cd ~/Emily1.0/web-solid && npx tsc --noEmit 2>&1 | head -20
```

Fix any import path issues. The files should compile cleanly since they have zero framework imports.

- [ ] **Step 6: Commit verbatim + adapted files**

```bash
cd ~/Emily1.0 && git add web-solid/src/api/ web-solid/src/lib/ web-solid/src/index.css
git commit -m "feat(web-solid): copy verbatim API/lib files, adapt icon imports for lucide-solid"
```

---

### Task 3: SolidJS Stores

**Files:**
- Create: `web-solid/src/stores/ui.ts`
- Create: `web-solid/src/stores/models.ts`
- Create: `web-solid/src/stores/chat.ts`
- Create: `web-solid/src/stores/brain.ts`
- Create: `web-solid/src/stores/onboarding.ts`

- [ ] **Step 1: Create stores directory**

```bash
mkdir -p ~/Emily1.0/web-solid/src/stores
```

- [ ] **Step 2: Create ui store**

```typescript
// stores/ui.ts
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
  const next = uiState.theme === 'dark' ? 'light' : 'dark'
  document.documentElement.classList.toggle('dark', next === 'dark')
  setUIState('theme', next)
}

export function setSearchOpen(open: boolean): void {
  setUIState('searchOpen', open)
}

export function setModeSelectorOpen(open: boolean): void {
  setUIState('modeSelectorOpen', open)
}

export function toggleRightPanel(): void {
  setUIState('rightPanelVisible', (v) => !v)
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
  setUIState({
    reasoningPanelSize: size,
    rightPanelVisible: size !== 'hidden',
  })
}

export function cycleReasoningPanel(): void {
  const idx = PANEL_CYCLE.indexOf(uiState.reasoningPanelSize)
  const next = PANEL_CYCLE[(idx + 1) % PANEL_CYCLE.length]
  setUIState({
    reasoningPanelSize: next,
    rightPanelVisible: next !== 'hidden',
  })
}
```

- [ ] **Step 3: Create models store**

```typescript
// stores/models.ts
import { createStore } from 'solid-js/store'
import { api } from '../api/client'
import { API_BASE } from '../lib/env'
import type { ModelSpec, Skill } from '../api/types'

export interface ModeInfo {
  id: string
  name: string
  display: string
  icon: string
  description: string
  reasoning_strategy: string
  reasoning_depth: number
  enable_thinking: boolean
  built_in: boolean
}

interface ModelsState {
  models: Record<string, ModelSpec>
  providers: Record<string, { available: boolean }>
  skills: Record<string, Skill>
  modes: Record<string, ModeInfo>
  activeModel: string
  activeSkill: string
  activeMode: string
}

const [modelsState, setModelsState] = createStore<ModelsState>({
  models: {},
  providers: {},
  skills: {},
  modes: {},
  activeModel: 'auto',
  activeSkill: 'normal',
  activeMode: 'normal',
})

export { modelsState }

export async function loadModels(): Promise<void> {
  const [modelsRes, providersRes] = await Promise.all([
    api.models.list(),
    api.models.providers(),
  ])
  setModelsState({ models: modelsRes.models, providers: providersRes.providers })
}

export async function loadSkills(): Promise<void> {
  const { skills } = await api.skills.list()
  setModelsState('skills', skills)
}

export async function loadModes(): Promise<void> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/modes`)
    if (res.ok) {
      const data = await res.json()
      setModelsState('modes', data.modes)
    }
  } catch {
    // Modes API not available yet
  }
}

export function setActiveModel(key: string): void {
  setModelsState('activeModel', key)
}

export function setActiveSkill(id: string): void {
  setModelsState('activeSkill', id)
}

export function setActiveMode(id: string): void {
  setModelsState('activeMode', id)
}
```

- [ ] **Step 4: Create chat store**

```typescript
// stores/chat.ts
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
  reasoningSteps: ReasoningStep[]
  skillProgress: SkillProgressEvent[]
  activeMode: string
  searchStatus: SearchEvent | null
  searchSources: Array<{ title: string; url: string }> | null
}

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
  const userMsg: Message = {
    id: crypto.randomUUID(),
    conversation_id: chatState.activeId ?? '',
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

  abortController = new AbortController()

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
      conversation_id: chatState.activeId,
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
      onReasoningStep: (data: ReasoningStepEvent) => {
        setChatState('reasoningSteps', produce((steps) => {
          steps.push({ ...data, timestamp: Date.now() })
        }))
      },
      onSkillProgress: (data: SkillProgressEvent) => {
        setChatState('skillProgress', produce((progress) => {
          progress.push(data)
        }))
      },
      onError: (msg) => {
        setChatState(produce((s) => {
          s.streamingText += `\n\n**Error:** ${msg}`
          s.isStreaming = false
        }))
      },
      onDone: () => {
        const assistantMsg: Message = {
          id: crypto.randomUUID(),
          conversation_id: chatState.activeId ?? '',
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
        loadConversations()
      },
    },
    abortController.signal,
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
```

- [ ] **Step 5: Create brain store**

```typescript
// stores/brain.ts
import { createStore, produce } from 'solid-js/store'
import { API_BASE, authHeaders } from '../lib/env'

export interface BrainEvent {
  id: string
  timestamp: string
  category: string
  event_type: string
  source: string
  data: Record<string, unknown>
  severity: string
}

interface BrainState {
  events: BrainEvent[]
  status: Record<string, unknown> | null
  agents: Array<Record<string, unknown>>
  models: Array<Record<string, unknown>>
  memoryData: Record<string, unknown> | null
  profiles: Array<Record<string, unknown>>
  auditLog: Array<Record<string, unknown>>
  selfImprovement: Record<string, unknown> | null
  emotionHistory: Array<Record<string, unknown>>
  workingMemory: Array<Record<string, unknown>>
}

const MAX_EVENTS = 500

const [brainState, setBrainState] = createStore<BrainState>({
  events: [],
  status: null,
  agents: [],
  models: [],
  memoryData: null,
  profiles: [],
  auditLog: [],
  selfImprovement: null,
  emotionHistory: [],
  workingMemory: [],
})

export { brainState }

export function pushEvents(newEvents: BrainEvent[]): void {
  setBrainState('events', produce((events) => {
    events.push(...newEvents)
    if (events.length > MAX_EVENTS) {
      events.splice(0, events.length - MAX_EVENTS)
    }
  }))
}

export function clearEvents(): void {
  setBrainState('events', [])
}

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { headers: authHeaders() })
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

export async function pollStatus(): Promise<void> {
  try {
    const data = await fetchJson<Record<string, unknown>>('/status')
    setBrainState('status', data)
  } catch { /* silent */ }
}

export async function pollAgents(): Promise<void> {
  try {
    const data = await fetchJson<{ agents: Array<Record<string, unknown>> }>('/agents')
    setBrainState('agents', data.agents)
  } catch { /* silent */ }
}

export async function loadBrainModels(): Promise<void> {
  try {
    const data = await fetchJson<{ models: Array<Record<string, unknown>> }>('/api/v1/models')
    setBrainState('models', data.models)
  } catch { /* silent */ }
}

export async function loadMemory(): Promise<void> {
  try {
    const data = await fetchJson<Record<string, unknown>>('/memory/status')
    setBrainState('memoryData', data)
  } catch { /* silent */ }
}

export async function loadProfiles(): Promise<void> {
  try {
    const data = await fetchJson<{ profiles: Array<Record<string, unknown>> }>('/api/v1/profiles')
    setBrainState('profiles', data.profiles)
  } catch { /* silent */ }
}

export async function loadAudit(): Promise<void> {
  try {
    const data = await fetchJson<{ entries: Array<Record<string, unknown>> }>('/api/v1/audit')
    setBrainState('auditLog', data.entries)
  } catch { /* silent */ }
}

export async function loadSelfImprovement(): Promise<void> {
  try {
    const data = await fetchJson<Record<string, unknown>>('/api/v1/self-improvement/status')
    setBrainState('selfImprovement', data)
  } catch { /* silent */ }
}

export async function loadEmotionHistory(): Promise<void> {
  try {
    const data = await fetchJson<{ history: Array<Record<string, unknown>> }>('/emotional-state/history')
    setBrainState('emotionHistory', data.history)
  } catch { /* silent */ }
}

export async function loadWorkingMemory(): Promise<void> {
  try {
    const data = await fetchJson<{ items: Array<Record<string, unknown>> }>('/memory/working')
    setBrainState('workingMemory', data.items)
  } catch { /* silent */ }
}
```

- [ ] **Step 6: Create onboarding store**

```typescript
// stores/onboarding.ts
import { createStore } from 'solid-js/store'

export type Phase = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7

export interface OnboardingData {
  name: string
  aiName: string
  voice: string
  voiceLabel: string
  passphrase: string
  email: string
}

interface OnboardingState {
  phase: Phase
  prevPhase: Phase | null
  transitioning: boolean
  data: OnboardingData
  isSpeaking: boolean
  inputVisible: boolean
  submitting: boolean
  error: string | null
  exiting: boolean
  mousePos: { x: number; y: number } | null
}

const initialData: OnboardingData = {
  name: '',
  aiName: '',
  voice: 'en-US-JennyNeural',
  voiceLabel: 'Jenny',
  passphrase: '',
  email: '',
}

const [onboardingState, setOnboardingState] = createStore<OnboardingState>({
  phase: 0,
  prevPhase: null,
  transitioning: false,
  data: { ...initialData },
  isSpeaking: false,
  inputVisible: false,
  submitting: false,
  error: null,
  exiting: false,
  mousePos: null,
})

export { onboardingState }

export function setPhase(p: Phase): void { setOnboardingState('phase', p) }

export function beginTransition(to: Phase): void {
  setOnboardingState({
    transitioning: true,
    prevPhase: onboardingState.phase,
    inputVisible: false,
    phase: to,
  })
}

export function completeTransition(): void { setOnboardingState('transitioning', false) }
export function setOnboardingData(partial: Partial<OnboardingData>): void {
  setOnboardingState('data', (prev) => ({ ...prev, ...partial }))
}
export function setIsSpeaking(v: boolean): void { setOnboardingState('isSpeaking', v) }
export function setInputVisible(v: boolean): void { setOnboardingState('inputVisible', v) }
export function setSubmitting(v: boolean): void { setOnboardingState('submitting', v) }
export function setOnboardingError(e: string | null): void { setOnboardingState('error', e) }
export function setExiting(v: boolean): void { setOnboardingState('exiting', v) }
export function setMousePos(pos: { x: number; y: number } | null): void { setOnboardingState('mousePos', pos) }
export function resetOnboarding(): void {
  setOnboardingState({
    phase: 0,
    prevPhase: null,
    transitioning: false,
    data: { ...initialData },
    isSpeaking: false,
    inputVisible: false,
    submitting: false,
    error: null,
    exiting: false,
  })
}
```

- [ ] **Step 7: Verify stores compile**

```bash
cd ~/Emily1.0/web-solid && npx tsc --noEmit 2>&1 | head -30
```

- [ ] **Step 8: Commit stores**

```bash
cd ~/Emily1.0 && git add web-solid/src/stores/
git commit -m "feat(web-solid): rewrite all 5 Zustand stores as SolidJS createStore"
```

---

### Task 4: SolidJS Primitives

**Files:**
- Create: `web-solid/src/primitives/createBrainWS.ts`
- Create: `web-solid/src/primitives/createKeyboard.ts`
- Create: `web-solid/src/primitives/createPolling.ts`
- Create: `web-solid/src/primitives/createModeAccent.ts`

- [ ] **Step 1: Create primitives directory**

```bash
mkdir -p ~/Emily1.0/web-solid/src/primitives
```

- [ ] **Step 2: Create createBrainWS with rAF batching**

```typescript
// primitives/createBrainWS.ts
import { onMount, onCleanup } from 'solid-js'
import { pushEvents, type BrainEvent } from '../stores/brain'
import { API_SECRET } from '../lib/env'

const PROD_TAURI = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

function getWsUrl(categories?: string[]): string {
  const base = PROD_TAURI ? 'ws://127.0.0.1:8001' : ''
  const params = new URLSearchParams()
  if (API_SECRET) params.set('token', API_SECRET)
  if (categories?.length) params.set('cats', categories.join(','))
  const qs = params.toString()
  return `${base}/ws/brain${qs ? '?' + qs : ''}`
}

export function createBrainWS(categories?: string[]): void {
  let ws: WebSocket | null = null
  let retryDelay = 2000
  let retryTimer: ReturnType<typeof setTimeout> | null = null
  let buffer: BrainEvent[] = []
  let rafId: number | null = null

  function flush(): void {
    if (buffer.length > 0) {
      pushEvents(buffer)
      buffer = []
    }
    rafId = null
  }

  function connect(): void {
    const url = getWsUrl(categories)
    ws = new WebSocket(url)

    ws.onopen = () => {
      retryDelay = 2000
    }

    ws.onmessage = (evt) => {
      try {
        const parsed = JSON.parse(evt.data) as BrainEvent | BrainEvent[]
        const events = Array.isArray(parsed) ? parsed : [parsed]
        buffer.push(...events)
        if (rafId === null) {
          rafId = requestAnimationFrame(flush)
        }
      } catch {
        // skip malformed JSON
      }
    }

    ws.onclose = () => {
      retryTimer = setTimeout(() => {
        retryDelay = Math.min(retryDelay * 1.5, 30000)
        connect()
      }, retryDelay)
    }

    ws.onerror = () => {
      ws?.close()
    }
  }

  onMount(() => {
    connect()
  })

  onCleanup(() => {
    if (retryTimer !== null) clearTimeout(retryTimer)
    if (rafId !== null) cancelAnimationFrame(rafId)
    ws?.close()
  })
}
```

- [ ] **Step 3: Create createKeyboard**

```typescript
// primitives/createKeyboard.ts
import { onMount, onCleanup } from 'solid-js'
import { uiState, setSearchOpen, setModeSelectorOpen } from '../stores/ui'
import { createConversation } from '../stores/chat'

export function createKeyboard(): void {
  function handler(e: KeyboardEvent): void {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault()
      setSearchOpen(!uiState.searchOpen)
    }

    if ((e.ctrlKey || e.metaKey) && e.key === 'm') {
      e.preventDefault()
      setModeSelectorOpen(!uiState.modeSelectorOpen)
    }

    if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
      e.preventDefault()
      createConversation()
    }
  }

  onMount(() => {
    window.addEventListener('keydown', handler)
  })

  onCleanup(() => {
    window.removeEventListener('keydown', handler)
  })
}
```

- [ ] **Step 4: Create createPolling**

```typescript
// primitives/createPolling.ts
import { createSignal, onMount, onCleanup } from 'solid-js'

interface PollingResult<T> {
  data: () => T | null
  loading: () => boolean
  error: () => string | null
  refetch: () => void
}

export function createPolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number,
): PollingResult<T> {
  const [data, setData] = createSignal<T | null>(null)
  const [loading, setLoading] = createSignal(true)
  const [error, setError] = createSignal<string | null>(null)

  async function doFetch(isFirst: boolean): Promise<void> {
    try {
      if (isFirst) setLoading(true)
      const result = await fetcher()
      setData(() => result)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      if (isFirst) setLoading(false)
    }
  }

  let intervalId: ReturnType<typeof setInterval> | null = null

  onMount(() => {
    doFetch(true)
    intervalId = setInterval(() => doFetch(false), intervalMs)
  })

  onCleanup(() => {
    if (intervalId !== null) clearInterval(intervalId)
  })

  return {
    data,
    loading,
    error,
    refetch: () => doFetch(false),
  }
}
```

- [ ] **Step 5: Create createModeAccent**

```typescript
// primitives/createModeAccent.ts
import { createEffect } from 'solid-js'
import { modelsState } from '../stores/models'
import { getModeTheme } from '../lib/mode-themes'

export function createModeAccent(): void {
  createEffect(() => {
    const theme = getModeTheme(modelsState.activeSkill)
    const root = document.documentElement
    root.style.setProperty('--color-mode-accent', theme.accent)
    root.style.setProperty('--color-mode-glow', theme.glow)
    root.style.setProperty('--mode-gradient', theme.gradient)
  })
}
```

- [ ] **Step 6: Verify primitives compile**

```bash
cd ~/Emily1.0/web-solid && npx tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 7: Commit primitives**

```bash
cd ~/Emily1.0 && git add web-solid/src/primitives/
git commit -m "feat(web-solid): SolidJS primitives — brain WS with rAF batching, keyboard, polling, mode accent"
```

---

## Phase 1: Chat Page (Kill Switch Critical)

### Task 5: Markdown Renderer + Code Block

**Files:**
- Create: `web-solid/src/components/markdown/MarkdownRenderer.tsx`
- Create: `web-solid/src/components/markdown/CodeBlock.tsx`

- [ ] **Step 1: Create markdown directory**

```bash
mkdir -p ~/Emily1.0/web-solid/src/components/markdown
```

- [ ] **Step 2: Create MarkdownRenderer**

```typescript
// components/markdown/MarkdownRenderer.tsx
import { createMemo } from 'solid-js'
import { unified } from 'unified'
import remarkParse from 'remark-parse'
import remarkGfm from 'remark-gfm'
import remarkRehype from 'remark-rehype'
import rehypeStringify from 'rehype-stringify'
import DOMPurify from 'dompurify'

interface Props {
  content: string
}

const processor = unified()
  .use(remarkParse)
  .use(remarkGfm)
  .use(remarkRehype)
  .use(rehypeStringify)

export function MarkdownRenderer(props: Props) {
  const html = createMemo(() => {
    const result = processor.processSync(props.content)
    return DOMPurify.sanitize(String(result))
  })

  return <div class="prose-emily" innerHTML={html()} />
}
```

**Note:** The processor instance is created once at module level — not per render. `processSync` is fine for chat-length content (<50KB). For very large documents, consider `createResource` with async `process()`.

- [ ] **Step 3: Create CodeBlock with Shiki**

```typescript
// components/markdown/CodeBlock.tsx
import { createSignal, createResource, Show } from 'solid-js'
import { codeToHtml } from 'shiki'
import { Copy, Check, ChevronDown, ChevronUp } from 'lucide-solid'

interface Props {
  code: string
  language?: string
}

export function CodeBlock(props: Props) {
  const [copied, setCopied] = createSignal(false)
  const [expanded, setExpanded] = createSignal(false)

  const lines = () => props.code.split('\n')
  const isLong = () => lines().length > 30
  const displayCode = () => isLong() && !expanded() ? lines().slice(0, 15).join('\n') : props.code
  const lang = () => props.language ?? 'text'

  const [html] = createResource(
    () => ({ code: displayCode(), lang: lang() }),
    ({ code, lang: l }) => codeToHtml(code, { lang: l, theme: 'one-dark-pro' }),
  )

  function handleCopy(): void {
    navigator.clipboard.writeText(props.code)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div class="my-3 rounded-xl border border-code-border overflow-hidden bg-code-bg">
      <div class="flex items-center justify-between px-4 py-2 bg-surface-hover/50 border-b border-code-border">
        <span class="text-xs font-mono text-text-muted uppercase">{lang()}</span>
        <button
          onClick={handleCopy}
          class="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-secondary transition-colors"
        >
          <Show when={copied()} fallback={<><Copy class="w-3.5 h-3.5" /> Copy</>}>
            <Check class="w-3.5 h-3.5 text-cost-green" /> Copied
          </Show>
        </button>
      </div>

      <Show
        when={html()}
        fallback={
          <pre class="p-4 text-[13px] leading-[1.6]" style={{ background: 'transparent' }}>
            {displayCode()}
          </pre>
        }
      >
        <div innerHTML={html()!} />
      </Show>

      <Show when={isLong()}>
        <button
          onClick={() => setExpanded((v) => !v)}
          class="w-full flex items-center justify-center gap-1 py-2 text-xs text-text-muted hover:text-text-secondary border-t border-code-border transition-colors"
        >
          <Show when={expanded()} fallback={<><ChevronDown class="w-3 h-3" /> Show all ({lines().length} lines)</>}>
            <ChevronUp class="w-3 h-3" /> Collapse
          </Show>
        </button>
      </Show>
    </div>
  )
}
```

- [ ] **Step 4: Commit markdown components**

```bash
cd ~/Emily1.0 && git add web-solid/src/components/markdown/
git commit -m "feat(web-solid): MarkdownRenderer (unified pipeline) + CodeBlock (Shiki)"
```

---

### Task 6: Chat Components

**Files:**
- Create: `web-solid/src/components/chat/UserMessage.tsx`
- Create: `web-solid/src/components/chat/EmilyMessage.tsx`
- Create: `web-solid/src/components/chat/MessageList.tsx`
- Create: `web-solid/src/components/chat/InputPanel.tsx`
- Create: `web-solid/src/components/chat/EmptyState.tsx`
- Create: `web-solid/src/components/common/ErrorBoundary.tsx`

- [ ] **Step 1: Create component directories**

```bash
mkdir -p ~/Emily1.0/web-solid/src/components/{chat,common}
```

- [ ] **Step 2: Create ErrorBoundary**

```typescript
// components/common/ErrorBoundary.tsx
import { ErrorBoundary as SolidErrorBoundary } from 'solid-js'
import type { ParentProps } from 'solid-js'

export function ErrorBoundary(props: ParentProps) {
  return (
    <SolidErrorBoundary
      fallback={(err) => (
        <div class="flex items-center justify-center p-8 text-error-red">
          <div class="text-center space-y-2">
            <p class="font-display font-semibold">Something went wrong</p>
            <p class="text-sm text-text-muted">{String(err)}</p>
          </div>
        </div>
      )}
    >
      {props.children}
    </SolidErrorBoundary>
  )
}
```

- [ ] **Step 3: Create UserMessage**

```typescript
// components/chat/UserMessage.tsx
import { createSignal } from 'solid-js'
import { Copy, Check } from 'lucide-solid'
import type { Message } from '../../api/types'

interface Props {
  message: Message
}

export function UserMessage(props: Props) {
  const [copied, setCopied] = createSignal(false)

  function handleCopy(): void {
    navigator.clipboard.writeText(props.message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div class="flex group justify-end">
      <div class="max-w-[82%] min-w-0 space-y-1">
        <div
          class="rounded-2xl rounded-tr-sm px-4 py-3"
          style={{ background: 'oklch(0.24 0.03 185)', border: '1px solid oklch(0.30 0.03 185 / 0.5)' }}
        >
          <p class="text-sm leading-relaxed whitespace-pre-wrap" style={{ color: 'oklch(0.93 0.01 90)', 'font-family': 'var(--font-body)' }}>
            {props.message.content}
          </p>
        </div>
        <div class="flex items-center gap-0.5 justify-end opacity-0 group-hover:opacity-100 transition-opacity pr-1">
          <button onClick={handleCopy} class="p-1 rounded-md transition-colors" style={{ color: 'oklch(0.50 0.04 185)' }} title="Copy">
            {copied() ? <Check class="w-3.5 h-3.5" style={{ color: 'oklch(0.72 0.15 145)' }} /> : <Copy class="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Create EmilyMessage**

Port the React component to SolidJS. Key changes: `props.x` access (never destructure), `createSignal` instead of `useState`, `Show` instead of ternary for complex conditions.

```typescript
// components/chat/EmilyMessage.tsx
import { createSignal, Show } from 'solid-js'
import { API_BASE } from '../../lib/env'
import {
  Copy, Check, ThumbsUp, ThumbsDown, RotateCcw,
  Brain, Volume2, Square, Sparkles, ChevronDown, ChevronRight, Globe,
} from 'lucide-solid'
import { MarkdownRenderer } from '../markdown/MarkdownRenderer'
import { rateMessage } from '../../stores/chat'
import { formatCost, formatLatency } from '../../lib/cost'
import { PROVIDER_COLORS } from '../../api/types'
import type { Message } from '../../api/types'

interface Props {
  message?: Message
  streaming?: boolean
  streamText?: string
  streamThinking?: string
  model?: string
  provider?: string
  searchSources?: Array<{ title: string; url: string }>
}

export function EmilyMessage(props: Props) {
  const [copied, setCopied] = createSignal(false)
  const [speaking, setSpeaking] = createSignal(false)
  const [thinkingCollapsed, setThinkingCollapsed] = createSignal(false)
  let audioRef: HTMLAudioElement | null = null

  const content = () => props.streaming ? (props.streamText ?? '') : (props.message?.content ?? '')
  const thinking = () => props.streaming ? (props.streamThinking ?? '') : (props.message?.thinking_content ?? '')
  const displayModel = () => props.model ?? props.message?.model ?? ''
  const displayProvider = () => props.provider ?? props.message?.provider ?? ''

  function handleCopy(): void {
    navigator.clipboard.writeText(content())
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  async function handleSpeak(): Promise<void> {
    if (speaking()) {
      audioRef?.pause()
      if (audioRef) audioRef.currentTime = 0
      setSpeaking(false)
      return
    }
    if (!content().trim()) return

    setSpeaking(true)
    try {
      const res = await fetch(`${API_BASE}/api/v1/tts/speak`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: content() }),
      })
      if (!res.ok) throw new Error(`TTS failed: ${res.status}`)

      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      audioRef = audio
      audio.onended = () => { setSpeaking(false); URL.revokeObjectURL(url) }
      audio.onerror = () => { setSpeaking(false); URL.revokeObjectURL(url) }
      await audio.play()
    } catch {
      setSpeaking(false)
    }
  }

  return (
    <div class="flex group gap-2.5 items-start">
      <div
        class="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5"
        style={{ background: 'oklch(0.72 0.17 162 / 0.12)', border: '1px solid oklch(0.72 0.17 162 / 0.28)' }}
      >
        <Sparkles class="w-3.5 h-3.5" style={{ color: 'oklch(0.72 0.17 162)' }} />
      </div>

      <div class="max-w-[82%] min-w-0 space-y-1.5">
        <span style={{ 'font-size': 'var(--text-small)', 'font-weight': 600, 'font-family': 'var(--font-display)', color: 'oklch(0.72 0.17 162)' }}>
          Emily
        </span>

        <Show when={thinking()}>
          <div class="rounded-xl overflow-hidden" style={{ border: '1px solid oklch(0.32 0.05 200)', background: 'oklch(0.19 0.025 200)' }}>
            <button
              onClick={() => !props.streaming && setThinkingCollapsed((v) => !v)}
              class="w-full flex items-center gap-2 px-3 py-2 transition-colors"
              style={{ 'font-size': 'var(--text-small)', color: 'oklch(0.72 0.17 162)', 'font-family': 'var(--font-body)', 'font-weight': 500 }}
            >
              <Show when={!props.streaming}>
                {thinkingCollapsed()
                  ? <ChevronRight class="w-3 h-3 flex-shrink-0" />
                  : <ChevronDown class="w-3 h-3 flex-shrink-0" />}
              </Show>
              <Brain class="w-3.5 h-3.5 flex-shrink-0" />
              <span>Thinking</span>
              <span class="font-normal ml-1" style={{ color: 'oklch(0.50 0.04 185)' }}>
                ~{Math.round(thinking().length / 4).toLocaleString()} tokens
              </span>
              <Show when={props.streaming}>
                <span class="flex items-center gap-1.5 ml-auto">
                  <span class="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: 'oklch(0.72 0.17 162)' }} />
                  <span style={{ 'font-size': '0.625rem', color: 'oklch(0.50 0.04 185)', 'font-family': 'var(--font-mono)' }}>live</span>
                </span>
              </Show>
            </button>
            <Show when={!thinkingCollapsed()}>
              <div class="px-3 pb-3" style={{ 'border-top': '1px solid oklch(0.32 0.05 200 / 0.5)' }}>
                <div class="leading-relaxed whitespace-pre-wrap max-h-64 overflow-y-auto mt-2"
                  style={{ 'font-size': 'var(--text-small)', color: 'oklch(0.50 0.04 185)', 'font-family': 'var(--font-body)' }}>
                  {thinking()}
                  <Show when={props.streaming}>
                    <span class="inline-block w-1 h-3 animate-pulse ml-0.5 -mb-0.5 rounded-sm" style={{ background: 'oklch(0.72 0.17 162)' }} />
                  </Show>
                </div>
              </div>
            </Show>
          </div>
        </Show>

        <div class="rounded-2xl rounded-tl-sm px-4 py-3" style={{ background: 'oklch(0.20 0.02 185)', border: '1px solid oklch(0.30 0.03 185 / 0.5)' }}>
          <Show when={content()} fallback={
            <Show when={props.streaming}>
              <div class="flex items-center gap-2" style={{ color: 'oklch(0.50 0.04 185)', 'font-size': 'var(--text-body)', 'font-family': 'var(--font-body)' }}>
                <span class="flex gap-1">
                  <span class="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: 'oklch(0.72 0.17 162)', 'animation-delay': '0ms' }} />
                  <span class="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: 'oklch(0.72 0.17 162)', 'animation-delay': '150ms' }} />
                  <span class="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: 'oklch(0.72 0.17 162)', 'animation-delay': '300ms' }} />
                </span>
                Emily is thinking...
              </div>
            </Show>
          }>
            <MarkdownRenderer content={content()} />
          </Show>
        </div>

        <Show when={props.searchSources && props.searchSources.length > 0}>
          <div class="flex flex-wrap gap-1.5 px-1">
            {props.searchSources?.map((s) => (
              <a
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                class="flex items-center gap-1 px-2 py-0.5 rounded-full transition-colors"
                style={{ 'font-size': 'var(--text-small)', color: 'oklch(0.65 0.03 185)', background: 'oklch(0.18 0.02 185)', border: '1px solid oklch(0.30 0.03 185)', 'font-family': 'var(--font-body)' }}
              >
                <Globe class="w-3 h-3" />
                <span class="max-w-[150px] truncate">{s.title}</span>
              </a>
            ))}
          </div>
        </Show>

        <div class="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity pl-1">
          <Show when={displayModel()}>
            <div class="flex items-center gap-1.5 mr-2" style={{ 'font-size': 'var(--text-small)', color: 'oklch(0.50 0.04 185)', 'font-family': 'var(--font-mono)' }}>
              <span class="w-1.5 h-1.5 rounded-full" style={{ 'background-color': PROVIDER_COLORS[displayProvider()] ?? 'oklch(0.50 0.04 185)' }} />
              <span>{displayModel()}</span>
            </div>
          </Show>

          <Show when={props.message && !props.streaming}>
            <Show when={props.message!.latency_ms != null}>
              <span class="mr-1" style={{ 'font-size': 'var(--text-small)', color: 'oklch(0.50 0.04 185)', 'font-family': 'var(--font-mono)' }}>
                {formatLatency(props.message!.latency_ms!)}
              </span>
            </Show>
            <Show when={props.message!.cost_usd > 0}>
              <span class="mr-1" style={{ 'font-size': 'var(--text-small)', color: 'oklch(0.72 0.15 145)', 'font-family': 'var(--font-mono)' }}>
                {formatCost(props.message!.cost_usd)}
              </span>
            </Show>
          </Show>

          <div class="flex items-center gap-0.5 ml-auto">
            <Show when={content() && !props.streaming}>
              <button onClick={handleSpeak} class="p-1 rounded-md transition-colors"
                style={{ color: speaking() ? 'oklch(0.72 0.17 162)' : 'oklch(0.50 0.04 185)', background: speaking() ? 'oklch(0.72 0.17 162 / 0.10)' : '' }}
                title={speaking() ? 'Stop reading' : 'Read aloud'}>
                {speaking() ? <Square class="w-3.5 h-3.5" /> : <Volume2 class="w-3.5 h-3.5" />}
              </button>
            </Show>

            <button onClick={handleCopy} class="p-1 rounded-md transition-colors" style={{ color: 'oklch(0.50 0.04 185)' }} title="Copy">
              {copied() ? <Check class="w-3.5 h-3.5" style={{ color: 'oklch(0.72 0.15 145)' }} /> : <Copy class="w-3.5 h-3.5" />}
            </button>

            <Show when={props.message && !props.streaming}>
              <button
                onClick={() => rateMessage(props.message!.id, props.message!.rating === 1 ? 0 : 1)}
                class="p-1 rounded-md transition-colors"
                style={{ color: props.message!.rating === 1 ? 'oklch(0.72 0.15 145)' : 'oklch(0.50 0.04 185)', background: props.message!.rating === 1 ? 'oklch(0.72 0.15 145 / 0.10)' : '' }}
                title="Good response">
                <ThumbsUp class="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => rateMessage(props.message!.id, props.message!.rating === -1 ? 0 : -1)}
                class="p-1 rounded-md transition-colors"
                style={{ color: props.message!.rating === -1 ? 'oklch(0.65 0.20 25)' : 'oklch(0.50 0.04 185)', background: props.message!.rating === -1 ? 'oklch(0.65 0.20 25 / 0.10)' : '' }}
                title="Bad response">
                <ThumbsDown class="w-3.5 h-3.5" />
              </button>
              <button class="p-1 rounded-md transition-colors" style={{ color: 'oklch(0.50 0.04 185)' }} title="Retry">
                <RotateCcw class="w-3.5 h-3.5" />
              </button>
            </Show>
          </div>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Create MessageList**

```typescript
// components/chat/MessageList.tsx
import { For, Show, onMount, createEffect } from 'solid-js'
import { Globe } from 'lucide-solid'
import { chatState } from '../../stores/chat'
import { UserMessage } from './UserMessage'
import { EmilyMessage } from './EmilyMessage'

export function MessageList() {
  let bottomRef: HTMLDivElement | undefined

  createEffect(() => {
    // Track these to trigger auto-scroll
    chatState.messages.length
    chatState.streamingText
    chatState.searchStatus
    bottomRef?.scrollIntoView({ behavior: 'smooth' })
  })

  return (
    <div class="flex-1 overflow-y-auto">
      <div class="max-w-4xl mx-auto px-4 py-6 space-y-6">
        <For each={chatState.messages}>
          {(msg) => (
            <Show when={msg.role === 'user'} fallback={
              <Show when={msg.role === 'assistant'}>
                <EmilyMessage message={msg} />
              </Show>
            }>
              <UserMessage message={msg} />
            </Show>
          )}
        </For>

        <Show when={chatState.isStreaming && chatState.searchStatus && chatState.searchStatus.status !== 'done'}>
          <div class="flex items-center gap-2 px-4 py-2 ml-9 text-xs text-text-muted">
            <Globe class="w-3.5 h-3.5 text-accent animate-pulse" />
            <span>
              {chatState.searchStatus?.status === 'searching' && 'Searching the web...'}
              {chatState.searchStatus?.status === 'found' && `Found ${chatState.searchStatus?.count} results`}
              {chatState.searchStatus?.status === 'reading' && (
                <>Reading: <span class="text-text-secondary">{chatState.searchStatus?.title}</span></>
              )}
              {chatState.searchStatus?.status === 'error' && (
                <span class="text-error-red">Search failed: {chatState.searchStatus?.message}</span>
              )}
            </span>
          </div>
        </Show>

        <Show when={chatState.isStreaming}>
          <EmilyMessage
            streaming
            streamText={chatState.streamingText}
            streamThinking={chatState.streamingThinking}
            model={chatState.streamMeta?.display ?? ''}
            provider={chatState.streamMeta?.provider ?? ''}
            searchSources={chatState.searchSources ?? undefined}
          />
        </Show>

        <div ref={bottomRef} />
      </div>
    </div>
  )
}
```

- [ ] **Step 6: Create InputPanel**

Port the React InputPanel. Key SolidJS changes: `createSignal` replaces `useState`, explicit `onInput`/`onKeyDown`, no `useRef` (use `let ref: HTMLElement | undefined`).

```typescript
// components/chat/InputPanel.tsx
import { createSignal, createEffect, Show, onCleanup } from 'solid-js'
import { Send, Square, Paperclip, Globe, Zap, X, Cpu, Layers } from 'lucide-solid'
import { chatState, sendMessage, stopGeneration, createConversation } from '../../stores/chat'
import { modelsState, setActiveSkill, setActiveMode } from '../../stores/models'
import { PROVIDER_COLORS } from '../../api/types'
import { getSkillIcon } from '../../lib/skill-icons'
import { getModeTheme } from '../../lib/mode-themes'

const SKILL_HINTS: Array<{ skill: string; name: string; pattern: RegExp }> = [
  { skill: 'translate', name: 'Translate', pattern: /\b(translate|in french|in spanish|in german|in japanese|in chinese|in arabic|in portuguese|in russian|in italian|en français|auf deutsch|en español|中文|日本語)\b/i },
  { skill: 'code', name: 'Code', pattern: /\b(function|class|debug|refactor|implement|algorithm|syntax error|runtime error|stack trace|python|javascript|typescript|rust|java|golang|sql|html|css|react|vue|fastapi|flask|django|api route|compile)\b/i },
  { skill: 'singing', name: 'Singing', pattern: /\bwrite (?:a )?(?:song|lyrics|rap|poem)\b|\bcompose (?:a )?(?:melody|song|music)\b/i },
  { skill: 'research', name: 'Research', pattern: /\b(find sources|look up|latest (?:news|research|studies)|cite|peer.?reviewed|evidence for|statistics on|data on)\b/i },
  { skill: 'writing', name: 'Writing', pattern: /\bwrite (?:a|an|me|my)\b|\b(draft|essay|blog post|article|cover letter|rewrite|proofread|improve (?:my|this) (?:writing|text|paragraph))\b/i },
  { skill: 'brainstorm', name: 'Brainstorm', pattern: /\b(brainstorm|give me \d* ?ideas|list \d* ?(?:ways|options|ideas)|different approaches|alternatives to)\b/i },
  { skill: 'deep_think', name: 'Deep Think', pattern: /\b(explain (?:in detail|deeply|thoroughly|step.?by.?step)|what causes|break.?down|implications of|evaluate the|analyze|analyse)\b/i },
]

function detectSkill(text: string): { skill: string; name: string } | null {
  if (text.length < 12) return null
  for (const hint of SKILL_HINTS) {
    if (hint.pattern.test(text)) return hint
  }
  return null
}

export function InputPanel() {
  const [text, setText] = createSignal('')
  const [webSearch, setWebSearch] = createSignal(false)
  const [attachments, setAttachments] = createSignal<File[]>([])
  const [suggestedSkill, setSuggestedSkill] = createSignal<{ skill: string; name: string } | null>(null)
  const [showModeDropdown, setShowModeDropdown] = createSignal(false)
  let textareaRef: HTMLTextAreaElement | undefined
  let fileInputRef: HTMLInputElement | undefined

  function adjustHeight(): void {
    if (!textareaRef) return
    textareaRef.style.height = 'auto'
    textareaRef.style.height = `${Math.min(textareaRef.scrollHeight, 220)}px`
  }

  createEffect(() => {
    text()
    adjustHeight()
  })

  // Debounced skill detection
  createEffect(() => {
    const t = text()
    const timer = setTimeout(() => {
      const detected = detectSkill(t)
      if (detected && detected.skill !== modelsState.activeSkill) {
        setSuggestedSkill(detected)
      } else {
        setSuggestedSkill(null)
      }
    }, 400)
    onCleanup(() => clearTimeout(timer))
  })

  async function handleSend(): Promise<void> {
    const trimmed = text().trim()
    if (!trimmed || chatState.isStreaming) return

    if (!chatState.activeId) {
      await createConversation(trimmed.slice(0, 50))
    }

    sendMessage(trimmed, modelsState.activeModel, modelsState.activeSkill, modelsState.activeMode, webSearch())
    setText('')
    setSuggestedSkill(null)
    textareaRef?.focus()
  }

  function handleKeyDown(e: KeyboardEvent): void {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function handleFiles(e: Event): void {
    const input = e.target as HTMLInputElement
    const files = Array.from(input.files ?? [])
    const valid = files.filter((f) => f.size <= 10 * 1024 * 1024)
    setAttachments((prev) => [...prev, ...valid])
    input.value = ''
  }

  function removeAttachment(idx: number): void {
    setAttachments((prev) => prev.filter((_, i) => i !== idx))
  }

  function formatSize(bytes: number): string {
    if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
    if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${bytes} B`
  }

  const resolvedModelKey = () =>
    chatState.isStreaming && chatState.streamMeta?.model_key
      ? chatState.streamMeta.model_key
      : modelsState.activeModel
  const modelSpec = () => resolvedModelKey() !== 'auto' ? modelsState.models[resolvedModelKey()] : null
  const modelDisplay = () =>
    resolvedModelKey() === 'auto' ? 'Auto' : (modelSpec()?.display?.replace('Emily — ', '') ?? resolvedModelKey())
  const providerColor = () => modelSpec() ? (PROVIDER_COLORS[modelSpec()!.provider] ?? '#555') : '#888'

  return (
    <div class="px-4 py-3 flex-shrink-0" style={{ 'border-top': '1px solid oklch(0.30 0.03 185)', background: 'oklch(0.22 0.025 185)' }}>
      <div class="max-w-4xl mx-auto space-y-2">
        <Show when={attachments().length > 0}>
          <div class="flex items-center gap-2 flex-wrap">
            {attachments().map((file, i) => (
              <div class="flex items-center gap-1.5 px-2.5 py-1 rounded-lg"
                style={{ background: 'oklch(0.18 0.02 185)', border: '1px solid oklch(0.30 0.03 185)', 'font-size': 'var(--text-small)', color: 'oklch(0.65 0.03 185)', 'font-family': 'var(--font-body)' }}>
                <Paperclip class="w-3 h-3" />
                <span class="max-w-[120px] truncate">{file.name}</span>
                <span class="text-text-muted">{formatSize(file.size)}</span>
                <button onClick={() => removeAttachment(i)} class="text-text-muted hover:text-error-red">
                  <X class="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
        </Show>

        <div class="flex items-end gap-2">
          <div class="flex-1 relative">
            <textarea
              ref={textareaRef}
              value={text()}
              onInput={(e) => setText(e.currentTarget.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask Emily anything..."
              rows={1}
              class="w-full resize-none rounded-xl px-4 py-3 pr-24 input-mode-border transition-colors leading-relaxed"
              style={{
                'min-height': '44px', 'max-height': '220px',
                background: 'oklch(0.18 0.02 185)', border: '1px solid oklch(0.30 0.03 185)',
                color: 'oklch(0.93 0.01 90)', 'font-size': 'var(--text-body)', 'font-family': 'var(--font-body)',
              }}
            />
            <div class="absolute right-2 bottom-2 flex items-center gap-1">
              <button onClick={() => fileInputRef?.click()} class="p-1.5 rounded-lg text-text-muted hover:text-text-secondary hover:bg-surface-hover transition-colors" title="Attach files">
                <Paperclip class="w-4 h-4" />
              </button>
              <button
                onClick={() => setWebSearch((v) => !v)}
                class={`p-1.5 rounded-lg transition-colors ${webSearch() ? 'text-accent bg-accent/10' : 'text-text-muted hover:text-text-secondary hover:bg-surface-hover'}`}
                title="Web search">
                <Globe class="w-4 h-4" />
              </button>
              <button class="p-1.5 rounded-lg text-text-muted hover:text-text-secondary hover:bg-surface-hover transition-colors" title="Quick mode">
                <Zap class="w-4 h-4" />
              </button>
            </div>
          </div>

          <Show when={chatState.isStreaming} fallback={
            <button
              onClick={handleSend}
              disabled={!text().trim()}
              class="p-3 rounded-xl transition-colors flex-shrink-0 disabled:opacity-30 disabled:cursor-not-allowed"
              style={{ background: 'oklch(0.72 0.17 162)', color: 'oklch(0.18 0.02 185)' }}
              title="Send message">
              <Send class="w-5 h-5" />
            </button>
          }>
            <button onClick={stopGeneration} class="p-3 rounded-xl transition-colors flex-shrink-0"
              style={{ background: 'oklch(0.65 0.20 25)', color: 'oklch(0.93 0.01 90)' }} title="Stop generation">
              <Square class="w-5 h-5" />
            </button>
          </Show>
        </div>

        <div class="flex items-center justify-between min-h-[20px]">
          <div class="flex items-center gap-1.5 text-xs text-text-muted">
            <Cpu class="w-3 h-3 flex-shrink-0" />
            <span class="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ 'background-color': providerColor() }} />
            <span class={chatState.isStreaming && chatState.streamMeta ? 'text-accent' : 'text-text-muted'}>
              {modelDisplay()}
            </span>
          </div>

          <Show when={suggestedSkill()}>
            {(skill) => (
              <div class="flex items-center gap-1.5">
                <span class="text-xs text-text-muted">Try:</span>
                <button
                  onClick={() => { setActiveSkill(skill().skill); setSuggestedSkill(null) }}
                  class="flex items-center gap-1 px-2 py-0.5 rounded-full bg-accent/10 border border-accent/30 text-xs text-accent hover:bg-accent/20 transition-colors">
                  <span>{skill().name}</span>
                </button>
                <button onClick={() => setSuggestedSkill(null)} class="text-text-muted hover:text-text-secondary transition-colors" title="Dismiss">
                  <X class="w-3 h-3" />
                </button>
              </div>
            )}
          </Show>
        </div>

        <input ref={fileInputRef} type="file" multiple class="hidden" onChange={handleFiles} />
      </div>
    </div>
  )
}
```

- [ ] **Step 7: Create EmptyState (simplified)**

```typescript
// components/chat/EmptyState.tsx
import { Sparkles } from 'lucide-solid'

export function EmptyState() {
  return (
    <div class="flex-1 flex items-center justify-center">
      <div class="text-center space-y-4 max-w-md">
        <div class="mx-auto w-16 h-16 rounded-full flex items-center justify-center"
          style={{ background: 'oklch(0.72 0.17 162 / 0.12)', border: '1px solid oklch(0.72 0.17 162 / 0.28)' }}>
          <Sparkles class="w-8 h-8" style={{ color: 'oklch(0.72 0.17 162)' }} />
        </div>
        <h2 class="font-display text-xl font-semibold text-text-primary">What can I help with?</h2>
        <p class="text-sm text-text-secondary" style={{ 'font-family': 'var(--font-body)' }}>
          Ask Emily anything. Press <kbd class="px-1.5 py-0.5 rounded bg-surface-hover text-text-muted text-xs font-mono">Ctrl+M</kbd> to switch modes,
          <kbd class="px-1.5 py-0.5 rounded bg-surface-hover text-text-muted text-xs font-mono ml-1">Ctrl+K</kbd> to search.
        </p>
      </div>
    </div>
  )
}
```

- [ ] **Step 8: Commit chat components**

```bash
cd ~/Emily1.0 && git add web-solid/src/components/chat/ web-solid/src/components/common/ web-solid/src/components/markdown/
git commit -m "feat(web-solid): chat components — MessageList, InputPanel, EmilyMessage, UserMessage, Markdown, CodeBlock"
```

---

### Task 7: Layout Shell + App Wiring

**Files:**
- Create: `web-solid/src/components/layout/AppNav.tsx`
- Create: `web-solid/src/components/layout/TopBar.tsx`
- Create: `web-solid/src/components/layout/Sidebar.tsx`
- Create: `web-solid/src/components/layout/MainLayout.tsx`
- Modify: `web-solid/src/App.tsx`

- [ ] **Step 1: Create layout directory**

```bash
mkdir -p ~/Emily1.0/web-solid/src/components/layout
```

- [ ] **Step 2: Create AppNav**

```typescript
// components/layout/AppNav.tsx
import { For } from 'solid-js'
import { MessageSquare, Mic, Eye, FileText, Brain, Terminal, Settings } from 'lucide-solid'
import { uiState, setActivePage, type AppPage } from '../../stores/ui'

const NAV_ITEMS: Array<{ id: AppPage; label: string; icon: typeof MessageSquare }> = [
  { id: 'chat', label: 'Chat', icon: MessageSquare },
  { id: 'voice', label: 'Voice', icon: Mic },
  { id: 'vision', label: 'Vision', icon: Eye },
  { id: 'logs', label: 'Logs', icon: FileText },
  { id: 'brain', label: 'Brain', icon: Brain },
  { id: 'terminal', label: 'Terminal', icon: Terminal },
  { id: 'settings', label: 'Settings', icon: Settings },
]

export function AppNav() {
  return (
    <nav class="flex items-center gap-0.5">
      <For each={NAV_ITEMS}>
        {(item) => {
          const Icon = item.icon
          return (
            <button
              onClick={() => setActivePage(item.id)}
              class={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs transition-colors ${
                uiState.activePage === item.id
                  ? 'text-accent bg-accent/10'
                  : 'text-text-muted hover:text-text-secondary hover:bg-surface-hover'
              }`}
            >
              <Icon class="w-3.5 h-3.5" />
              <span>{item.label}</span>
            </button>
          )
        }}
      </For>
    </nav>
  )
}
```

- [ ] **Step 3: Create TopBar (simplified — model selector deferred to after kill switch)**

```typescript
// components/layout/TopBar.tsx
import { AppNav } from './AppNav'
import { cycleReasoningPanel } from '../../stores/ui'
import { PanelRight } from 'lucide-solid'

export function TopBar() {
  return (
    <div
      class="flex items-center justify-between px-4 py-2 flex-shrink-0"
      style={{ 'border-bottom': '1px solid oklch(0.30 0.03 185)', background: 'oklch(0.20 0.02 185)' }}
      data-tauri-drag-region
    >
      <AppNav />
      <div class="flex items-center gap-2">
        <button
          onClick={cycleReasoningPanel}
          class="p-1.5 rounded-lg text-text-muted hover:text-text-secondary hover:bg-surface-hover transition-colors"
          title="Toggle reasoning panel (Ctrl+Shift+R)"
        >
          <PanelRight class="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Create Sidebar (minimal — conversation list)**

Read the full React Sidebar from `web/src/components/layout/Sidebar.tsx` during implementation and port it. For the kill switch gate, a minimal version is sufficient:

```typescript
// components/layout/Sidebar.tsx
import { For, Show, createSignal } from 'solid-js'
import { Plus, MessageSquare } from 'lucide-solid'
import { chatState, loadConversations, selectConversation, createConversation } from '../../stores/chat'
import { relativeTime } from '../../lib/time'

export function Sidebar() {
  return (
    <div
      class="w-[260px] h-full flex flex-col flex-shrink-0"
      style={{ 'border-right': '1px solid oklch(0.30 0.03 185)', background: 'oklch(0.16 0.02 185)' }}
    >
      <div class="p-3">
        <button
          onClick={() => createConversation()}
          class="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-text-secondary hover:bg-surface-hover transition-colors"
          style={{ border: '1px solid oklch(0.30 0.03 185)' }}
        >
          <Plus class="w-4 h-4" />
          <span>New conversation</span>
        </button>
      </div>

      <div class="flex-1 overflow-y-auto px-2 space-y-0.5">
        <For each={chatState.conversations}>
          {(conv) => (
            <button
              onClick={() => selectConversation(conv.id)}
              class={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors truncate ${
                chatState.activeId === conv.id
                  ? 'bg-surface-hover text-text-primary'
                  : 'text-text-secondary hover:bg-surface-hover/50'
              }`}
            >
              <div class="flex items-center gap-2">
                <MessageSquare class="w-3.5 h-3.5 flex-shrink-0 text-text-muted" />
                <span class="truncate">{conv.title}</span>
              </div>
              <div class="text-xs text-text-muted mt-0.5 pl-5.5">
                {relativeTime(conv.updated_at)}
              </div>
            </button>
          )}
        </For>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Create MainLayout**

```typescript
// components/layout/MainLayout.tsx
import { Show, Switch, Match, createEffect, onMount } from 'solid-js'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'
import { MessageList } from '../chat/MessageList'
import { InputPanel } from '../chat/InputPanel'
import { EmptyState } from '../chat/EmptyState'
import { ErrorBoundary } from '../common/ErrorBoundary'
import { uiState, setAuthenticated, setRightPanelVisible, setReasoningPanelSize } from '../../stores/ui'
import { chatState } from '../../stores/chat'
import { createModeAccent } from '../../primitives/createModeAccent'
import { createKeyboard } from '../../primitives/createKeyboard'
import { API_RAW } from '../../lib/env'

export function MainLayout() {
  createModeAccent()
  createKeyboard()

  let prevThinking = ''

  // Auto-open reasoning panel on thinking stream
  createEffect(() => {
    if (chatState.streamingThinking && !prevThinking) {
      setRightPanelVisible(true)
      if (uiState.reasoningPanelSize === 'hidden') {
        setReasoningPanelSize('sidebar')
      }
    }
    prevThinking = chatState.streamingThinking
  })

  // Auth check on mount
  onMount(() => {
    fetch(`${API_RAW}/settings/auth/status`)
      .then((r) => r.json())
      .then((d) => {
        if (!d.passphrase_set || !d.has_owner) {
          setAuthenticated(true)
        }
      })
      .catch(() => setAuthenticated(true))
  })

  // TODO: LoginScreen will be added in Task 11

  return (
    <Show when={uiState.authenticated} fallback={
      <div class="flex h-screen w-screen items-center justify-center bg-surface text-text-primary">
        <p class="text-text-muted">Authenticating...</p>
      </div>
    }>
      <div class="flex h-screen w-screen overflow-hidden bg-surface">
        <Show when={uiState.activePage === 'chat'}>
          <aside aria-label="Conversations">
            <Sidebar />
          </aside>
        </Show>

        <main class="flex flex-1 flex-col min-w-0">
          <header>
            <TopBar />
          </header>

          <Switch fallback={
            <div class="flex flex-1 min-h-0">
              <div class="flex flex-1 flex-col min-w-0">
                <Show when={chatState.activeId} fallback={<EmptyState />}>
                  <MessageList />
                  <InputPanel />
                </Show>
              </div>
            </div>
          }>
            <Match when={uiState.activePage === 'brain'}>
              <ErrorBoundary>
                <div class="flex-1 flex items-center justify-center text-text-muted">
                  Brain page — Task 8
                </div>
              </ErrorBoundary>
            </Match>
            <Match when={uiState.activePage === 'settings'}>
              <ErrorBoundary>
                <div class="flex-1 flex items-center justify-center text-text-muted">
                  Settings page — Task 9
                </div>
              </ErrorBoundary>
            </Match>
            <Match when={uiState.activePage === 'voice'}>
              <div class="flex-1 flex items-center justify-center text-text-muted">Voice page — Task 10</div>
            </Match>
            <Match when={uiState.activePage === 'vision'}>
              <div class="flex-1 flex items-center justify-center text-text-muted">Vision page — Task 10</div>
            </Match>
            <Match when={uiState.activePage === 'logs'}>
              <div class="flex-1 flex items-center justify-center text-text-muted">Logs page — Task 10</div>
            </Match>
            <Match when={uiState.activePage === 'terminal'}>
              <div class="flex-1 flex items-center justify-center text-text-muted">Terminal page — Task 10</div>
            </Match>
          </Switch>
        </main>
      </div>
    </Show>
  )
}
```

- [ ] **Step 6: Update App.tsx**

```typescript
// App.tsx
import type { Component } from 'solid-js'
import { onMount } from 'solid-js'
import { MainLayout } from './components/layout/MainLayout'
import { ErrorBoundary } from './components/common/ErrorBoundary'
import { loadConversations } from './stores/chat'
import { loadModels, loadSkills, loadModes } from './stores/models'

const App: Component = () => {
  onMount(() => {
    loadConversations()
    loadModels()
    loadSkills()
    loadModes()
  })

  return (
    <ErrorBoundary>
      <MainLayout />
    </ErrorBoundary>
  )
}

export default App
```

- [ ] **Step 7: Verify compilation and dev server**

```bash
cd ~/Emily1.0/web-solid && npx tsc --noEmit 2>&1 | head -30
# Fix any errors
npx vite --port 1421 &
# Open http://127.0.0.1:1421 in browser, verify app loads
# Kill the dev server
```

- [ ] **Step 8: Commit layout + app wiring**

```bash
cd ~/Emily1.0 && git add web-solid/src/components/layout/ web-solid/src/App.tsx
git commit -m "feat(web-solid): layout shell + chat page wiring — kill switch foundation"
```

---

## Phase 2: Brain Page (Kill Switch Critical)

### Task 8: Brain Page + EventStream

**Files:**
- Create: `web-solid/src/pages/BrainPage.tsx`
- Create: `web-solid/src/components/brain/BrainTabs.tsx`
- Create: `web-solid/src/components/brain/NeuralOverview.tsx`
- Create: `web-solid/src/components/brain/EventStream.tsx`
- Create: `web-solid/src/components/charts/ProgressRing.tsx`

The Brain page is the second kill-switch gate. The critical component is EventStream with virtualized `<For>` and the WebSocket integration.

- [ ] **Step 1: Create directories**

```bash
mkdir -p ~/Emily1.0/web-solid/src/{pages,components/brain,components/charts}
```

- [ ] **Step 2: Create BrainTabs**

```typescript
// components/brain/BrainTabs.tsx
import { For } from 'solid-js'
import { Activity, Heart, Cpu, Database, Server, User, Radio, MessageSquare } from 'lucide-solid'

export type BrainTab = 'neural' | 'emotional' | 'cognitive' | 'memory' | 'fleet' | 'personality' | 'stream' | 'chat'

const TABS: Array<{ id: BrainTab; label: string; icon: typeof Activity }> = [
  { id: 'neural', label: 'NEURAL', icon: Activity },
  { id: 'emotional', label: 'EMOTION', icon: Heart },
  { id: 'cognitive', label: 'COGNIT', icon: Cpu },
  { id: 'memory', label: 'MEMORY', icon: Database },
  { id: 'fleet', label: 'FLEET', icon: Server },
  { id: 'personality', label: 'PERSONA', icon: User },
  { id: 'stream', label: 'STREAM', icon: Radio },
  { id: 'chat', label: 'QUERY', icon: MessageSquare },
]

interface Props {
  active: BrainTab
  onChange: (tab: BrainTab) => void
}

export function BrainTabs(props: Props) {
  return (
    <div class="flex gap-0.5 px-3 py-2" style={{ 'border-bottom': '1px solid oklch(0.30 0.03 185)' }}>
      <For each={TABS}>
        {(tab) => {
          const Icon = tab.icon
          return (
            <button
              onClick={() => props.onChange(tab.id)}
              class={`flex items-center gap-1.5 px-2.5 py-1.5 rounded text-[10px] font-mono tracking-wider transition-colors ${
                props.active === tab.id
                  ? 'text-phosphor-green bg-phosphor-green/10 border border-phosphor-green/30'
                  : 'text-readout-dim hover:text-text-secondary border border-transparent'
              }`}
            >
              <Icon class="w-3 h-3" />
              {tab.label}
            </button>
          )
        }}
      </For>
    </div>
  )
}
```

- [ ] **Step 3: Create ProgressRing**

```typescript
// components/charts/ProgressRing.tsx
interface Props {
  value: number
  max: number
  size?: number
  label?: string
  color?: string
  format?: (value: number, max: number) => string
}

export function ProgressRing(props: Props) {
  const size = () => props.size ?? 80
  const radius = () => (size() - 8) / 2
  const circumference = () => 2 * Math.PI * radius()
  const progress = () => props.max > 0 ? Math.min(props.value / props.max, 1) : 0
  const dashOffset = () => circumference() * (1 - progress())
  const color = () => props.color ?? 'oklch(0.72 0.17 162)'
  const display = () => props.format ? props.format(props.value, props.max) : `${Math.round(progress() * 100)}%`

  return (
    <div class="flex flex-col items-center gap-1">
      <svg width={size()} height={size()} class="transform -rotate-90">
        <circle
          cx={size() / 2} cy={size() / 2} r={radius()}
          fill="none" stroke="oklch(0.24 0.015 185)" stroke-width="4"
        />
        <circle
          cx={size() / 2} cy={size() / 2} r={radius()}
          fill="none" stroke={color()} stroke-width="4"
          stroke-dasharray={circumference()} stroke-dashoffset={dashOffset()}
          stroke-linecap="round"
          style={{ transition: 'stroke-dashoffset 0.5s ease' }}
        />
      </svg>
      <div class="text-center">
        <span class="text-xs font-mono tabular-nums" style={{ color: color() }}>{display()}</span>
        {props.label && <p class="text-[10px] text-readout-dim">{props.label}</p>}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Create NeuralOverview (simplified)**

```typescript
// components/brain/NeuralOverview.tsx
import { Show } from 'solid-js'
import { brainState } from '../../stores/brain'
import { ProgressRing } from '../charts/ProgressRing'

export function NeuralOverview() {
  const fsmState = () => (brainState.status as Record<string, unknown> | null)?.fsm_state as string ?? 'UNKNOWN'
  const cpu = () => (brainState.status as Record<string, unknown> | null)?.cpu_percent as number ?? 0
  const ram = () => (brainState.status as Record<string, unknown> | null)?.ram_percent as number ?? 0
  const vram = () => (brainState.status as Record<string, unknown> | null)?.vram_percent as number ?? 0

  return (
    <div class="p-4 space-y-6">
      <div class="text-center">
        <div
          class="inline-block px-4 py-2 rounded-lg font-mono text-sm tracking-wider animate-pulse-ring"
          style={{ color: 'oklch(0.72 0.17 162)', border: '1px solid oklch(0.72 0.17 162 / 0.3)', background: 'oklch(0.72 0.17 162 / 0.05)' }}
        >
          {fsmState()}
        </div>
      </div>

      <div class="flex justify-center gap-6">
        <ProgressRing value={cpu()} max={100} label="CPU" color="oklch(0.72 0.17 162)" />
        <ProgressRing value={ram()} max={100} label="RAM" color="oklch(0.75 0.16 85)" />
        <ProgressRing value={vram()} max={100} label="VRAM" color="oklch(0.65 0.20 25)" />
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Create EventStream with @tanstack/solid-virtual**

This is the critical virtualized list that justifies the SolidJS migration.

```typescript
// components/brain/EventStream.tsx
import { createSignal, createMemo, For, Show } from 'solid-js'
import { createVirtualizer } from '@tanstack/solid-virtual'
import { brainState } from '../../stores/brain'
import type { BrainEvent } from '../../stores/brain'

const CATEGORY_COLORS: Record<string, string> = {
  llm: 'oklch(0.72 0.17 162)',
  fsm: 'oklch(0.75 0.16 85)',
  agent: 'oklch(0.65 0.20 350)',
  memory: 'oklch(0.60 0.15 230)',
  tool: 'oklch(0.70 0.19 45)',
  voice: 'oklch(0.73 0.18 55)',
  system: 'oklch(0.65 0.03 185)',
}

export function EventStream() {
  const [filter, setFilter] = createSignal<string | null>(null)
  let scrollRef: HTMLDivElement | undefined

  const filteredEvents = createMemo(() => {
    const f = filter()
    if (!f) return brainState.events
    return brainState.events.filter((e) => e.category === f)
  })

  const virtualizer = createVirtualizer({
    get count() { return filteredEvents().length },
    getScrollElement: () => scrollRef ?? null,
    estimateSize: () => 28,
    overscan: 20,
  })

  return (
    <div class="h-full flex flex-col">
      <div class="flex items-center gap-2 px-3 py-2" style={{ 'border-bottom': '1px solid oklch(0.30 0.03 185)' }}>
        <span class="w-2 h-2 rounded-full animate-rec-blink" style={{ background: 'oklch(0.65 0.20 25)' }} />
        <span class="text-[10px] font-mono text-readout-dim">REC</span>
        <span class="text-[10px] font-mono tabular-nums text-phosphor-green ml-auto">
          {brainState.events.length} events
        </span>
      </div>

      <div class="flex gap-1 px-3 py-1.5 flex-wrap" style={{ 'border-bottom': '1px solid oklch(0.24 0.015 185)' }}>
        <button
          onClick={() => setFilter(null)}
          class={`px-2 py-0.5 rounded text-[10px] font-mono ${!filter() ? 'text-phosphor-green bg-phosphor-green/10' : 'text-readout-dim hover:text-text-secondary'}`}
        >
          ALL
        </button>
        {Object.keys(CATEGORY_COLORS).map((cat) => (
          <button
            onClick={() => setFilter(filter() === cat ? null : cat)}
            class={`px-2 py-0.5 rounded text-[10px] font-mono ${filter() === cat ? 'bg-phosphor-green/10' : 'hover:bg-surface-hover/50'}`}
            style={{ color: filter() === cat ? CATEGORY_COLORS[cat] : 'oklch(0.50 0.04 185)' }}
          >
            {cat.toUpperCase()}
          </button>
        ))}
      </div>

      <div ref={scrollRef} class="flex-1 overflow-y-auto" style={{ contain: 'strict' }}>
        <div style={{ height: `${virtualizer.getTotalSize()}px`, width: '100%', position: 'relative' }}>
          <For each={virtualizer.getVirtualItems()}>
            {(virtualRow) => {
              const event = () => filteredEvents()[virtualRow.index]
              return (
                <div
                  class="absolute top-0 left-0 w-full flex items-center gap-2 px-3 text-[11px] font-mono"
                  style={{
                    height: `${virtualRow.size}px`,
                    transform: `translateY(${virtualRow.start}px)`,
                  }}
                >
                  <span class="text-readout-dim tabular-nums w-20 flex-shrink-0">
                    {new Date(event().timestamp).toLocaleTimeString('en-US', { hour12: false, fractionalSecondDigits: 1 })}
                  </span>
                  <span
                    class="w-1.5 h-1.5 rounded-full flex-shrink-0"
                    style={{ background: CATEGORY_COLORS[event().category] ?? 'oklch(0.50 0.04 185)' }}
                  />
                  <span class="text-readout-dim w-14 flex-shrink-0 uppercase text-[9px]">{event().category}</span>
                  <span class="text-phosphor-green truncate">{event().event_type}</span>
                  <span class="text-readout-dim truncate ml-auto">{event().source}</span>
                </div>
              )
            }}
          </For>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 6: Create BrainPage**

```typescript
// pages/BrainPage.tsx
import { createSignal, Switch, Match } from 'solid-js'
import { BrainTabs, type BrainTab } from '../components/brain/BrainTabs'
import { NeuralOverview } from '../components/brain/NeuralOverview'
import { EventStream } from '../components/brain/EventStream'
import { createBrainWS } from '../primitives/createBrainWS'
import { createPolling } from '../primitives/createPolling'
import { pollStatus, pollAgents, loadBrainModels, loadMemory, loadProfiles } from '../stores/brain'

export function BrainPage() {
  const [activeTab, setActiveTab] = createSignal<BrainTab>('neural')

  // Connect brain WebSocket
  createBrainWS()

  // Poll status and agents
  createPolling(pollStatus, 10_000)
  createPolling(pollAgents, 30_000)
  createPolling(loadBrainModels, 30_000)
  createPolling(loadMemory, 30_000)
  createPolling(loadProfiles, 30_000)

  return (
    <div class="flex-1 flex flex-col min-h-0 data-lab-grid" style={{ 'background-size': '32px 32px' }}>
      <BrainTabs active={activeTab()} onChange={setActiveTab} />

      <div class="flex-1 min-h-0 overflow-hidden">
        <Switch fallback={
          <div class="flex-1 flex items-center justify-center text-readout-dim font-mono text-sm">
            {activeTab().toUpperCase()} — coming soon
          </div>
        }>
          <Match when={activeTab() === 'neural'}>
            <NeuralOverview />
          </Match>
          <Match when={activeTab() === 'stream'}>
            <EventStream />
          </Match>
        </Switch>
      </div>
    </div>
  )
}
```

- [ ] **Step 7: Wire BrainPage into MainLayout**

Replace the placeholder in `MainLayout.tsx`:

```typescript
// In the Switch block, replace the brain Match:
import { BrainPage } from '../../pages/BrainPage'

// ...
<Match when={uiState.activePage === 'brain'}>
  <ErrorBoundary>
    <BrainPage />
  </ErrorBoundary>
</Match>
```

- [ ] **Step 8: Verify brain page works**

```bash
cd ~/Emily1.0/web-solid && npx tsc --noEmit 2>&1 | head -30
# Start Emily API server if not running: cd ~/Emily1.0 && uv run uvicorn api.app:app --host 127.0.0.1 --port 8001 --reload &
# Start dev server: npx vite --port 1421
# Navigate to Brain tab, verify:
# 1. BrainTabs render
# 2. NeuralOverview shows FSM state + resource rings
# 3. EventStream tab shows virtualized event list
# 4. WebSocket connects and events flow in
```

- [ ] **Step 9: Commit brain page**

```bash
cd ~/Emily1.0 && git add web-solid/src/pages/BrainPage.tsx web-solid/src/components/brain/ web-solid/src/components/charts/
git commit -m "feat(web-solid): brain page — virtualized EventStream + WebSocket + rAF batching"
```

---

## Phase 3: Settings Page

### Task 9: Settings Page (Decomposed)

**Files:**
- Create: `web-solid/src/pages/SettingsPage.tsx`
- Create: `web-solid/src/pages/settings/ProfileSettings.tsx`
- Create: `web-solid/src/pages/settings/PersonaSettings.tsx`
- Create: `web-solid/src/pages/settings/PermissionsSettings.tsx`
- Create: `web-solid/src/pages/settings/AudioSettings.tsx`
- Create: `web-solid/src/pages/settings/AdvancedSettings.tsx`

The React SettingsPage is a 1720-LOC monolith. We decompose it into 5 focused sub-components. Read `web/src/pages/SettingsPage.tsx` during implementation and port each section.

- [ ] **Step 1: Create settings directory**

```bash
mkdir -p ~/Emily1.0/web-solid/src/pages/settings
```

- [ ] **Step 2: Create SettingsPage shell with tab navigation**

```typescript
// pages/SettingsPage.tsx
import { createSignal, Switch, Match, lazy } from 'solid-js'
import { User, Sparkles, Shield, Volume2, Wrench } from 'lucide-solid'

const ProfileSettings = lazy(() => import('./settings/ProfileSettings'))
const PersonaSettings = lazy(() => import('./settings/PersonaSettings'))
const PermissionsSettings = lazy(() => import('./settings/PermissionsSettings'))
const AudioSettings = lazy(() => import('./settings/AudioSettings'))
const AdvancedSettings = lazy(() => import('./settings/AdvancedSettings'))

type SettingsTab = 'profile' | 'persona' | 'permissions' | 'audio' | 'advanced'

const TABS: Array<{ id: SettingsTab; label: string; icon: typeof User }> = [
  { id: 'profile', label: 'Profile', icon: User },
  { id: 'persona', label: 'Persona', icon: Sparkles },
  { id: 'permissions', label: 'Permissions', icon: Shield },
  { id: 'audio', label: 'Audio', icon: Volume2 },
  { id: 'advanced', label: 'Advanced', icon: Wrench },
]

export function SettingsPage() {
  const [activeTab, setActiveTab] = createSignal<SettingsTab>('profile')

  return (
    <div class="flex-1 flex min-h-0">
      <nav class="w-48 flex-shrink-0 p-4 space-y-1" style={{ 'border-right': '1px solid oklch(0.30 0.03 185)' }}>
        {TABS.map((tab) => {
          const Icon = tab.icon
          return (
            <button
              onClick={() => setActiveTab(tab.id)}
              class={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
                activeTab() === tab.id
                  ? 'text-accent bg-accent/10'
                  : 'text-text-secondary hover:bg-surface-hover'
              }`}
            >
              <Icon class="w-4 h-4" />
              {tab.label}
            </button>
          )
        })}
      </nav>

      <div class="flex-1 overflow-y-auto p-6">
        <Switch>
          <Match when={activeTab() === 'profile'}><ProfileSettings /></Match>
          <Match when={activeTab() === 'persona'}><PersonaSettings /></Match>
          <Match when={activeTab() === 'permissions'}><PermissionsSettings /></Match>
          <Match when={activeTab() === 'audio'}><AudioSettings /></Match>
          <Match when={activeTab() === 'advanced'}><AdvancedSettings /></Match>
        </Switch>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Create sub-component stubs**

Each settings sub-component should be created by reading the corresponding section from `web/src/pages/SettingsPage.tsx` and porting it. Create working stubs first, then port incrementally.

For each of the 5 files (`ProfileSettings.tsx`, `PersonaSettings.tsx`, `PermissionsSettings.tsx`, `AudioSettings.tsx`, `AdvancedSettings.tsx`), create a stub:

```typescript
// pages/settings/ProfileSettings.tsx (example — same pattern for all 5)
export default function ProfileSettings() {
  return (
    <div class="max-w-2xl space-y-6">
      <h2 class="font-display text-lg font-semibold text-text-primary">Profile</h2>
      <p class="text-sm text-text-muted">Owner profile, authentication, and API keys settings.</p>
      {/* Port from web/src/pages/SettingsPage.tsx Owner Profile section */}
    </div>
  )
}
```

Create all 5 stubs with appropriate headings and descriptions. The implementation agent will read the original SettingsPage and fill these in.

- [ ] **Step 4: Wire SettingsPage into MainLayout**

Import and replace the placeholder in MainLayout.tsx:

```typescript
import { SettingsPage } from '../../pages/SettingsPage'

// In the Switch:
<Match when={uiState.activePage === 'settings'}>
  <ErrorBoundary>
    <SettingsPage />
  </ErrorBoundary>
</Match>
```

- [ ] **Step 5: Commit settings page**

```bash
cd ~/Emily1.0 && git add web-solid/src/pages/
git commit -m "feat(web-solid): settings page shell with 5 decomposed sub-components"
```

---

## Phase 4: Remaining Pages + Polish

### Task 10: Remaining Pages (Voice, Logs, Vision, Terminal)

**Files:**
- Create: `web-solid/src/pages/VoicePage.tsx`
- Create: `web-solid/src/pages/LogsPage.tsx`
- Create: `web-solid/src/pages/VisionPage.tsx`
- Create: `web-solid/src/pages/TerminalPage.tsx`

These pages are NOT on the kill switch critical path. Port from the React versions by reading the corresponding files in `web/src/pages/`.

- [ ] **Step 1: Create each page by porting from React**

For each page, the implementation agent should:
1. Read the React version from `web/src/pages/<PageName>.tsx`
2. Port to SolidJS: `createSignal` instead of `useState`, `createEffect` instead of `useEffect`, `<For>` instead of `.map()`, `<Show>` instead of ternaries, `props.x` instead of destructured props
3. Replace `lucide-react` imports with `lucide-solid`
4. Replace Zustand `useXStore((s) => s.x)` with direct `xState.x` access

- [ ] **Step 2: Wire all pages into MainLayout**

Replace all remaining placeholders in the Switch block with actual page components.

- [ ] **Step 3: Commit remaining pages**

```bash
cd ~/Emily1.0 && git add web-solid/src/pages/ web-solid/src/components/
git commit -m "feat(web-solid): remaining pages — Voice, Logs, Vision, Terminal"
```

---

### Task 11: Auth + Search + ModeSelector

**Files:**
- Create: `web-solid/src/components/auth/LoginScreen.tsx`
- Create: `web-solid/src/components/search/SearchOverlay.tsx`
- Create: `web-solid/src/components/chat/ModeSelector.tsx`

Port from React versions. These are overlay/modal components.

- [ ] **Step 1: Port LoginScreen, SearchOverlay, ModeSelector from React**

Read each React source and port to SolidJS following the same patterns as chat components.

- [ ] **Step 2: Wire into MainLayout**

- `LoginScreen`: shown when `!uiState.authenticated`
- `SearchOverlay`: shown when `uiState.searchOpen`
- `ModeSelector`: always mounted (controls own visibility)

- [ ] **Step 3: Commit auth + overlays**

```bash
cd ~/Emily1.0 && git add web-solid/src/components/auth/ web-solid/src/components/search/ web-solid/src/components/chat/ModeSelector.tsx
git commit -m "feat(web-solid): auth login, search overlay, mode selector"
```

---

### Task 12: Reasoning Panel

**Files:**
- Create: `web-solid/src/components/reasoning/ReasoningPanelV2.tsx`
- Create: `web-solid/src/components/reasoning/ThinkingPhases.tsx`
- Create: `web-solid/src/components/reasoning/FlowDiagram.tsx`
- Create: `web-solid/src/components/reasoning/ReasoningTimeline.tsx`
- Create: `web-solid/src/components/reasoning/ModelComparison.tsx`
- Create: `web-solid/src/components/reasoning/MemoryInsight.tsx`
- Create: `web-solid/src/components/reasoning/ReasoningMetrics.tsx`

Port from React versions in `web/src/components/reasoning/`.

- [ ] **Step 1: Port all reasoning components**

- [ ] **Step 2: Wire ReasoningPanelV2 into MainLayout chat view**

- [ ] **Step 3: Commit reasoning panel**

```bash
cd ~/Emily1.0 && git add web-solid/src/components/reasoning/
git commit -m "feat(web-solid): reasoning panel with thinking phases, flow diagram, timeline"
```

---

### Task 13: Remaining Brain Components

**Files:**
- Create: `web-solid/src/components/brain/EmotionalCortex.tsx`
- Create: `web-solid/src/components/brain/CognitiveProcesses.tsx`
- Create: `web-solid/src/components/brain/MemoryArchitecture.tsx`
- Create: `web-solid/src/components/brain/ModelFleet.tsx`
- Create: `web-solid/src/components/brain/PersonalityMatrix.tsx`
- Create: `web-solid/src/components/brain/BrainChat.tsx`
- Create: `web-solid/src/components/charts/RadarChart.tsx`
- Create: `web-solid/src/components/charts/Sparkline.tsx`
- Create: `web-solid/src/components/charts/DonutChart.tsx`
- Create: `web-solid/src/components/charts/BarChart.tsx`

Port remaining brain dashboard components and charts from React versions.

- [ ] **Step 1: Port all remaining brain + chart components**

- [ ] **Step 2: Wire into BrainPage Switch block**

- [ ] **Step 3: Commit remaining brain components**

```bash
cd ~/Emily1.0 && git add web-solid/src/components/brain/ web-solid/src/components/charts/
git commit -m "feat(web-solid): remaining brain dashboard components + charts"
```

---

### Task 14: Tauri Build Verification

- [ ] **Step 1: Update tauri.conf.json devUrl if needed**

The symlinked `src-tauri/tauri.conf.json` points to `http://127.0.0.1:1420`. For the SolidJS app on port 1421, we may need a separate config or to start the dev server on 1420 when working on the SolidJS version.

Options:
- A: Change `devUrl` to 1421 when working on SolidJS (requires editing the shared config)
- B: Copy `tauri.conf.json` instead of symlinking, update port

Choose B — copy and adapt:

```bash
cd ~/Emily1.0/web-solid
rm src-tauri  # remove symlink
cp -r ../web/src-tauri ./src-tauri
```

Edit `src-tauri/tauri.conf.json`: change `devUrl` to `http://127.0.0.1:1421`.

- [ ] **Step 2: Build Tauri app**

```bash
cd ~/Emily1.0/web-solid && npm run tauri build 2>&1 | tail -20
```

- [ ] **Step 3: Verify AppImage runs**

```bash
ls ~/Emily1.0/web-solid/src-tauri/target/release/bundle/appimage/
# Run the AppImage and verify it loads
```

- [ ] **Step 4: Commit Tauri config**

```bash
cd ~/Emily1.0 && git add web-solid/src-tauri/
git commit -m "feat(web-solid): copy Tauri config for SolidJS build (port 1421)"
```

---

## Acceptance Checklist

After all tasks are complete, verify against spec acceptance criteria:

- [ ] All 7 pages functional (Chat, Brain, Settings, Voice, Logs, Vision, Terminal)
- [ ] WebSocket brain events stream into `<For>` (no full-list re-render)
- [ ] SSE chat streaming works with abort/stop
- [ ] At least 40 of 128 API endpoints wired (same as React app)
- [ ] Tauri build produces working AppImage
- [ ] EventStream handles 100 events/sec without frame drops
- [ ] React app preserved in `web/` (unmodified)

---

## Kill Switch Gate (Day 5)

If by day 5 these two conditions are NOT met:

1. Chat page works end-to-end (send message → receive SSE stream → render markdown)
2. Brain WebSocket streams events into virtualized `<For>` list

**Then abandon `web-solid/` and apply these React fixes to `web/` instead:**

1. `@tanstack/react-virtual` on EventStream
2. `React.memo` on EventRow
3. Ring buffer in pushEvents (replace array spread)
4. `requestAnimationFrame` batching in useBrainWS
