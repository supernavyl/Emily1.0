import {
  Languages, Code2, Music, FlaskConical, PenLine,
  Lightbulb, Brain, Zap, MessageSquare,
  Mic, BarChart3, GraduationCap, Swords, Sparkles,
  GitCompareArrows, Megaphone, Share2, Clapperboard, TrendingUp,
} from 'lucide-solid'
import type { LucideIcon } from 'lucide-solid'

const SKILL_ICON_MAP: Record<string, LucideIcon> = {
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

export function getSkillIcon(id: string): LucideIcon {
  return SKILL_ICON_MAP[id] ?? Zap
}
