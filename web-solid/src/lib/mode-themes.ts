import type { LucideIcon } from 'lucide-solid'
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
  icon: LucideIcon
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
    description: 'Devil\'s advocate, counterarguments, critical analysis',
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
    description: 'Explain like I\'m five — simple, fun, visual',
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
