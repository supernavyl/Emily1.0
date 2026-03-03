import type { LucideIcon } from 'lucide-react'
import {
  MessageSquare, Brain, Code2, FlaskConical, BarChart3, TrendingUp,
  PenLine, Lightbulb, Music, Clapperboard,
  Megaphone, Share2,
  Mic, Zap, GraduationCap, Swords, Sparkles,
  Languages, GitCompareArrows,
} from 'lucide-react'

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
    gradient: 'linear-gradient(135deg, #7c6af7, #6366f1)',
    gradientStops: ['#7c6af7', '#6366f1'],
    glow: 'rgba(124, 106, 247, 0.35)',
    accent: '#7c6af7',
    icon: MessageSquare,
    category: 'communication',
    capabilities: [],
    temperature: 0.7,
  },
  {
    id: 'deep_think',
    name: 'Deep Think',
    description: 'Extended reasoning and step-by-step analysis',
    gradient: 'linear-gradient(135deg, #6366f1, #8b5cf6, #4f46e5)',
    gradientStops: ['#6366f1', '#4f46e5'],
    glow: 'rgba(99, 102, 241, 0.35)',
    accent: '#8b5cf6',
    icon: Brain,
    category: 'thinking',
    capabilities: ['thinking'],
    temperature: 0.3,
  },
  {
    id: 'code',
    name: 'Code',
    description: 'Programming, debugging, and technical implementation',
    gradient: 'linear-gradient(135deg, #10b981, #06b6d4)',
    gradientStops: ['#10b981', '#06b6d4'],
    glow: 'rgba(16, 185, 129, 0.35)',
    accent: '#10b981',
    icon: Code2,
    category: 'thinking',
    capabilities: ['thinking', 'code_exec'],
    temperature: 0.2,
  },
  {
    id: 'research',
    name: 'Research',
    description: 'Deep investigation with sources and citations',
    gradient: 'linear-gradient(135deg, #3b82f6, #6366f1)',
    gradientStops: ['#3b82f6', '#6366f1'],
    glow: 'rgba(59, 130, 246, 0.35)',
    accent: '#3b82f6',
    icon: FlaskConical,
    category: 'thinking',
    capabilities: ['thinking', 'web_search'],
    temperature: 0.4,
  },
  {
    id: 'analyst',
    name: 'Analyst',
    description: 'Data analysis, metrics, and quantitative reasoning',
    gradient: 'linear-gradient(135deg, #60a5fa, #3b82f6)',
    gradientStops: ['#60a5fa', '#3b82f6'],
    glow: 'rgba(96, 165, 250, 0.35)',
    accent: '#60a5fa',
    icon: BarChart3,
    category: 'thinking',
    capabilities: ['thinking', 'code_exec'],
    temperature: 0.3,
  },
  {
    id: 'market_research',
    name: 'Market Research',
    description: 'Market trends, competitor analysis, and industry insights',
    gradient: 'linear-gradient(135deg, #0d9488, #0891b2)',
    gradientStops: ['#0d9488', '#0891b2'],
    glow: 'rgba(13, 148, 136, 0.35)',
    accent: '#0d9488',
    icon: TrendingUp,
    category: 'thinking',
    capabilities: ['thinking', 'web_search'],
    temperature: 0.4,
  },
  {
    id: 'writing',
    name: 'Writing',
    description: 'Creative and professional writing, editing, prose',
    gradient: 'linear-gradient(135deg, #f43f5e, #ec4899)',
    gradientStops: ['#f43f5e', '#ec4899'],
    glow: 'rgba(244, 63, 94, 0.35)',
    accent: '#f43f5e',
    icon: PenLine,
    category: 'creative',
    capabilities: [],
    temperature: 0.8,
  },
  {
    id: 'brainstorm',
    name: 'Brainstorm',
    description: 'Divergent thinking, idea generation, creative exploration',
    gradient: 'linear-gradient(135deg, #eab308, #f59e0b)',
    gradientStops: ['#eab308', '#f59e0b'],
    glow: 'rgba(234, 179, 8, 0.35)',
    accent: '#eab308',
    icon: Lightbulb,
    category: 'creative',
    capabilities: ['thinking'],
    temperature: 0.9,
  },
  {
    id: 'singing',
    name: 'Singing',
    description: 'Songwriting, lyrics, melody composition',
    gradient: 'linear-gradient(135deg, #a855f7, #ec4899)',
    gradientStops: ['#a855f7', '#ec4899'],
    glow: 'rgba(168, 85, 247, 0.35)',
    accent: '#a855f7',
    icon: Music,
    category: 'creative',
    capabilities: [],
    temperature: 0.85,
  },
  {
    id: 'video_script',
    name: 'Video Script',
    description: 'Screenwriting, video scripts, storyboarding',
    gradient: 'linear-gradient(135deg, #f97316, #ef4444)',
    gradientStops: ['#f97316', '#ef4444'],
    glow: 'rgba(249, 115, 22, 0.35)',
    accent: '#f97316',
    icon: Clapperboard,
    category: 'creative',
    capabilities: [],
    temperature: 0.8,
  },
  {
    id: 'ad_copywriter',
    name: 'Ad Copywriter',
    description: 'Persuasive copy, headlines, marketing content',
    gradient: 'linear-gradient(135deg, #ec4899, #f43f5e)',
    gradientStops: ['#ec4899', '#f43f5e'],
    glow: 'rgba(236, 72, 153, 0.35)',
    accent: '#ec4899',
    icon: Megaphone,
    category: 'professional',
    capabilities: [],
    temperature: 0.75,
  },
  {
    id: 'social_media',
    name: 'Social Media',
    description: 'Platform-specific content, engagement strategy',
    gradient: 'linear-gradient(135deg, #d946ef, #f43f5e)',
    gradientStops: ['#d946ef', '#f43f5e'],
    glow: 'rgba(217, 70, 239, 0.35)',
    accent: '#d946ef',
    icon: Share2,
    category: 'professional',
    capabilities: ['web_search'],
    temperature: 0.75,
  },
  {
    id: 'voice',
    name: 'Voice',
    description: 'Conversational, speech-optimized responses',
    gradient: 'linear-gradient(135deg, #fb923c, #f97316)',
    gradientStops: ['#fb923c', '#f97316'],
    glow: 'rgba(251, 146, 60, 0.35)',
    accent: '#fb923c',
    icon: Mic,
    category: 'communication',
    capabilities: [],
    temperature: 0.7,
  },
  {
    id: 'concise',
    name: 'Concise',
    description: 'Short, direct answers without fluff',
    gradient: 'linear-gradient(135deg, #06b6d4, #0ea5e9)',
    gradientStops: ['#06b6d4', '#0ea5e9'],
    glow: 'rgba(6, 182, 212, 0.35)',
    accent: '#06b6d4',
    icon: Zap,
    category: 'communication',
    capabilities: [],
    temperature: 0.5,
  },
  {
    id: 'tutor',
    name: 'Tutor',
    description: 'Patient teaching, explanations, guided learning',
    gradient: 'linear-gradient(135deg, #22c55e, #14b8a6)',
    gradientStops: ['#22c55e', '#14b8a6'],
    glow: 'rgba(34, 197, 94, 0.35)',
    accent: '#22c55e',
    icon: GraduationCap,
    category: 'communication',
    capabilities: ['thinking'],
    temperature: 0.6,
  },
  {
    id: 'debate',
    name: 'Debate',
    description: 'Devil\'s advocate, counterarguments, critical analysis',
    gradient: 'linear-gradient(135deg, #ef4444, #dc2626)',
    gradientStops: ['#ef4444', '#dc2626'],
    glow: 'rgba(239, 68, 68, 0.35)',
    accent: '#ef4444',
    icon: Swords,
    category: 'communication',
    capabilities: ['thinking'],
    temperature: 0.7,
  },
  {
    id: 'eli5',
    name: 'ELI5',
    description: 'Explain like I\'m five — simple, fun, visual',
    gradient: 'linear-gradient(135deg, #c084fc, #e879f9)',
    gradientStops: ['#c084fc', '#e879f9'],
    glow: 'rgba(192, 132, 252, 0.35)',
    accent: '#c084fc',
    icon: Sparkles,
    category: 'communication',
    capabilities: [],
    temperature: 0.8,
  },
  {
    id: 'translate',
    name: 'Translate',
    description: 'Multi-language translation and localization',
    gradient: 'linear-gradient(135deg, #0ea5e9, #8b5cf6)',
    gradientStops: ['#0ea5e9', '#8b5cf6'],
    glow: 'rgba(14, 165, 233, 0.35)',
    accent: '#0ea5e9',
    icon: Languages,
    category: 'utility',
    capabilities: [],
    temperature: 0.3,
  },
  {
    id: 'compare',
    name: 'Compare',
    description: 'Side-by-side comparisons, pros and cons',
    gradient: 'linear-gradient(135deg, #818cf8, #6366f1)',
    gradientStops: ['#818cf8', '#6366f1'],
    glow: 'rgba(129, 140, 248, 0.35)',
    accent: '#818cf8',
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
