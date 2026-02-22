# Emily — Psychoacoustics Model

> How Emily models human conversational behavior.

---

## Foundational Principles

Emily's voice engine is built on three pillars of conversational psychoacoustics:

1. **Turn-taking is signal-based, not silence-based**
2. **Backchannels create the perception of active listening**
3. **Rhythm entrainment builds unconscious rapport**

## Turn-Taking Model

Humans predict turn completion 200-300ms before it occurs using multiple
converging signals. Emily replicates this with a 14-signal fusion engine.

### Signal Categories

**Acoustic signals** (processed in < 5ms):
- **Final intonation**: Falling F0 = declarative completion. Rising F0 = question.
  Level F0 = still mid-utterance. F0 reset to baseline = strong completion.
- **Final lengthening**: Humans stretch the last syllable of a turn.
  Duration of final vowel vs speaker baseline indicates turn-ending.
- **Energy decay**: Gradual energy reduction over last 200ms (not sudden stop).
- **Breath detection**: Post-utterance inhalation is one of the strongest
  completion signals. Classifier trained on breath vs fricative vs silence.
- **Glottalization**: Creaky voice / vocal fry at utterance end indicates completion.
  Common in American English.

**Linguistic signals** (processed in < 10ms):
- **Syntactic completeness**: Nano LLM evaluates whether the partial transcript
  forms a complete sentence. "I went to the..." → 0.1. "I went to the store." → 0.95.
- **Backchannel elicitors**: "you know?", "right?", "doesn't it?" invite response.
- **Discourse markers**: "anyway", "so yeah", "that's pretty much it" signal completion.
- **Question detection**: Rising intonation + syntactic question form + question words.

**Contextual signals** (processed in < 20ms):
- **Topic exhaustion**: Has the speaker covered all branches of their topic?
- **Response urgency**: Emotional topics → faster response. Complex questions → natural delay.

### Signal Weights

```
final_intonation:       0.22
syntactic_completeness: 0.20
breath_detected:        0.15
silence_duration:       0.10
final_lengthening:      0.08
discourse_marker:       0.07
question_detected:      0.06
energy_decay:           0.04
backchannel_elicitor:   0.03
glottalization:         0.02
topic_exhaustion:       0.01
gaze_shift:             0.01
gesture_completion:     0.01
```

Thresholds: RESPOND at 0.85, BACKCHANNEL at 0.45, OVERLAP_START at 0.95.

## Backchannel Model

Backchannels are listener vocalizations that signal attention without claiming the turn.

### Six Types

| Type | Function | Examples | Timing |
|------|----------|----------|--------|
| Continuer | "I'm listening" | mmhm, yeah, uh-huh | Phrase boundaries |
| Acknowledgment | "I understood" | I see, got it, okay | After new info |
| Agreement | "I agree" | exactly, totally | After evaluative statement |
| Empathy | "I feel you" | oh wow, of course, oh no | After emotional content |
| Surprise | "That's unexpected" | oh really?, huh, no way | After unexpected info |
| Completion | "I know what you'll say" | finish their sentence | Prediction > 0.90 |

### Rules

- Maximum 1 backchannel per 4 seconds
- Volume: 30-40% of normal speaking volume
- Never overlap stressed syllables
- Insert at inter-pausal unit boundaries
- Never the same token twice consecutively
- 40+ variants per type for diversity
- Prosody: upspeak on continuers, flat on acknowledgments

## Rhythm Entrainment Model

Based on Communication Accommodation Theory: speakers who entrain their rhythm
to their interlocutor are perceived as more likable, trustworthy, and intelligent.

### What Emily Synchronizes

- **Speaking rate** (syllables per second)
- **Pause duration patterns** (between phrases, between sentences)
- **Prosodic phrase length** (words per breath group)
- **Inter-turn gap** (response latency)
- **Breathing rhythm** (if detectable)

### Entrainment Degree

Tunable from 0.0 (no sync) to 1.0 (full mirror). Default: 0.4.
At 0.4, the synchronization is noticeable but not uncanny.

Cross-session memory stores per-user rhythm profiles in Emily's episodic memory.

## Emotion Adaptation Model

### Detection

- Primary: prosody features (pitch, rate, energy patterns)
- Secondary: lexical content (word choice analysis)
- 10 emotion categories: neutral, happy, excited, anxious, frustrated, sad,
  confused, curious, bored, tired

### Adaptation Rules

- **Mirror positive emotions**: User excited → Emily becomes warmer, more energetic
- **Calm negative emotions**: User anxious → Emily becomes steadier, slower
- **Never amplify negative emotions**: User angry → Emily stays calm
- **Energy match within +/- 20%**: Never wildly mismatched
- **Adapt vocabulary complexity**: Simpler when user is tired or stressed
- **Adapt sentence length**: Shorter when user is frustrated or impatient

## Interruption Psychology

### Six Interrupt Types

| Type | User intent | Emily response |
|------|-------------|---------------|
| Cooperative overlap | Finishing Emily's sentence | Stop gracefully, no acknowledgment |
| Content interrupt | Adding information | "oh—", "yes—" + stop + listen |
| Clarification | Asking a question | "oh sure" + stop + listen |
| Correction | Correcting Emily | "oh, sorry" + stop + listen |
| Urgency | Something important | Immediately silent |
| Disengagement | Done with topic | "right, yeah" + stop |

### Graceful Trail-off

Emily never stops mid-word. The interrupt handler:
1. Finds the nearest word boundary within 300ms lookahead in the TTS buffer
2. Applies a 20ms audio fade at that boundary
3. Emits appropriate acknowledgment vocalization
4. Preserves response context for potential resumption

## Filler and Breathing Model

### Fillers

Cover processing latency with natural thinking sounds:
- **Immediate** (0-100ms): breath intake, "hmm..."
- **Short** (100-500ms): "let me think...", "good question..."
- **Medium** (500-1500ms): "that's a good point, let me think..."
- **Long** (> 1500ms): "give me just a second..."

All fillers are pre-rendered at startup. They blend into the first word
of the real response via 50ms crossfade.

### Breathing

- Before sentences > 8 words: natural inhale
- After emotional sentences: audible exhale
- Random micro-breaths every 15-25 seconds
- Volume: 15-25% of speech level
- 20+ breath samples matched to speaking energy
