# How to Train Emily

Emily doesn't need traditional ML "training" — she learns through **5 systems** that work together automatically. Here's how each one works and how you control it.

---

## Quick Reference

| Method | What It Does | How You Do It |
|--------|-------------|---------------|
| **Just Talk** | Emily remembers everything | Have conversations |
| **Drop Files** | Feed her knowledge | Put files in `knowledge/` |
| **Correct Her** | She learns from mistakes | Say "that's wrong, actually..." |
| **Rate Responses** | Improves prompt quality | 👍/👎 in the chat UI |
| **Edit Persona** | Change her personality | Edit `persona/profile.json` |

---

## 1. Conversational Learning (Automatic)

**Emily learns from every conversation.** Just talk to her.

Every interaction is:
- Saved to `data/interactions.db` immediately (crash-safe)
- Stored in **episodic memory** (session summaries)
- Extracted into **semantic memory** (facts, entities, relationships)
- Used to update **procedural memory** (your preferences, her self-model)

### What She Remembers

| You Say | Emily Stores |
|---------|-------------|
| "I'm a developer at Google" | Fact: occupation = developer at Google |
| "I prefer concise answers" | Preference: communication_style = concise |
| "I'm working on a Rust project" | Context: active_project = Rust project |
| "My wife's name is Sarah" | Relationship: wife = Sarah |
| "I hate mushrooms" | Preference: dislikes = mushrooms |

### How To Train Through Conversation

```
You:   "Remember that I always want code examples in Python, not JavaScript"
Emily: "Got it! I'll always default to Python for code examples."

You:   "When I say 'deploy', I mean push to my home server at 192.168.1.50"
Emily: "Understood. 'Deploy' means push to 192.168.1.50."
```

**Tip:** Be explicit. Say "remember this" for important facts.

---

## 2. Knowledge Feeding (RAG)

**Drop files into the `knowledge/` folder.** Emily automatically ingests them.

### Supported Formats

| Format | Extension |
|--------|-----------|
| Documents | `.pdf`, `.docx`, `.epub`, `.txt`, `.md`, `.html` |
| Code | `.py`, `.js`, `.ts`, `.rs`, `.go`, `.java`, `.ipynb` |
| Data | `.csv`, `.json`, `.yaml` |
| Media | `.mp3`, `.wav`, `.m4a` (transcribed), `.mp4`, `.mkv` |
| Presentations | `.pptx` |

### How It Works

```
knowledge/
├── my_notes.md          ← drop file here
├── research_paper.pdf   ← Emily auto-ingests
├── codebase/            ← entire folders work too
│   ├── main.py
│   └── utils.py
└── meeting_recording.mp3  ← transcribed and indexed
```

The `RAGFileWatcher` monitors `knowledge/` and auto-processes new files:

1. **Parse** → Extract text from the file format
2. **Chunk** → Split into 256-token child chunks + 2048-token parent chunks
3. **Embed** → BGE-M3 embeddings (dense + sparse + multi-vector)
4. **Store** → Qdrant vector database + BM25 sparse index
5. **Graph** → Extract entities and relationships → knowledge graph

### After Ingestion

```
You:   "What does that research paper say about transformer attention?"
Emily: "According to the paper you shared, transformer attention..."
       (cites the actual document)
```

### Manual Ingestion

```bash
# Ingest a specific file
python -c "
import asyncio
from rag.ingestor import DocumentIngestor
from config import get_settings
s = get_settings()
ing = DocumentIngestor(s.rag)
asyncio.run(ing.ingest_file('path/to/file.pdf'))
"
```

---

## 3. Correction & Feedback (Active Learning)

**Emily learns from your corrections.** When she's wrong, tell her.

### Correcting Facts

```
Emily: "Your meeting is at 3 PM."
You:   "No, it's at 4 PM. Please update that."
Emily: "Corrected! Meeting time updated to 4 PM."
```

Emily updates her memory tiers and adjusts confidence scores on retrieved chunks.

### Rating Responses

In the Tauri chat UI, you can 👍/👎 responses. This feeds the **RAG Feedback Loop**:

- **👍** → Positive signal → retrieved chunks get relevance boost
- **👎** → Negative signal → chunks penalized in future retrieval
- Low-quality documents flagged for re-ingestion

### Performance Tracking

Every response is automatically scored:
- **CriticAgent** rates: accuracy, completeness, safety, helpfulness (0-1)
- **Latency** tracked: STT, LLM, TTS timings
- **RAG quality**: relevance scores, hit rates

All tracked in `data/performance_log.jsonl`.

---

## 4. Prompt Evolution (Self-Improvement)

**Emily automatically evolves her own prompts** using A/B testing.

### How It Works

1. Emily has **prompt variants** for each slot (system prompt, RAG prompt, etc.)
2. Variants compete via **epsilon-greedy bandit** strategy
3. After enough samples, the best-performing variant is **promoted**
4. Old versions archived to `prompts/archive/`

### What Gets Evolved

| Prompt Slot | What It Controls |
|-------------|-----------------|
| `system_prompt` | Emily's core personality and behavior |
| `rag_prompt` | How she uses retrieved context |
| `critic_prompt` | How she self-evaluates response quality |
| `reflection_prompt` | How she generates insights during idle time |
| `onboarding_prompt` | How she conducts owner onboarding |

### Monitoring Evolution

```bash
# Check prompt stats
cat data/prompt_stats.json | python -m json.tool

# View archived prompts
ls prompts/archive/
```

### Manual Prompt Editing

All prompts live in `llm/prompt_builder.py`. You can edit directly:

```python
# In llm/prompt_builder.py
_EMILY_SYSTEM_PROMPT_V1 = """\
You are Emily - a persistent, intelligent AI companion...
"""
```

**Rule:** Always archive the old version first:
```bash
cp prompts/system_prompt_v1.txt prompts/archive/system_prompt_v1_$(date +%F).txt
```

---

## 5. Capability Gap Resolution (Auto-Growth)

**When Emily can't do something, she logs it and learns to handle it.**

### The Gap → Tool → Skill Pipeline

```
1. Emily fails a task
   ↓
2. CapabilityGapLogger records it (data/capability_gaps.jsonl)
   ↓
3. ToolBuilderAgent drafts a new tool (using smart model)
   ↓
4. You review and approve the tool
   ↓
5. Tool saved to plugins/generated/ and loaded
   ↓
6. Successful tool sequences saved to skill library
```

### Gap Types

| Type | Meaning |
|------|---------|
| `tool_missing` | Needs a tool that doesn't exist |
| `knowledge_gap` | RAG returned nothing relevant |
| `reasoning_failure` | ReAct loop couldn't solve it |
| `skill_gap` | Needs a multi-step skill she hasn't learned |
| `model_limitation` | LLM tier was insufficient |

### Viewing Gaps

```bash
# See unresolved capability gaps
cat data/capability_gaps.jsonl | python -m json.tool | head -100
```

---

## 6. Reflection (Idle-Time Growth)

**When Emily is idle, she reflects on past conversations and improves.**

The `ReflectionAgent` runs automatically during quiet periods:

1. Reviews recent **episodic memories** (last 5 sessions)
2. Generates **insights** using the smart model
3. Updates **self-model** (capabilities, limitations, strategies)
4. Updates **persona** trajectory
5. Triggers **prompt evolution** if patterns are detected

### Manual Reflection

```
You: "Emily, reflect on today's conversations"
Emily: "Let me think about that... [generates insights]"
```

---

## 7. Persona Tuning

**Adjust Emily's personality directly.**

### Edit `persona/profile.json`

```json
{
  "curiosity": 0.8,      // 0=disinterested, 1=extremely curious
  "warmth": 0.85,        // 0=cold, 1=very warm
  "directness": 0.7,     // 0=indirect, 1=blunt
  "humor": 0.5,          // 0=serious, 1=very playful
  "formality": 0.3       // 0=casual, 1=formal
}
```

### Or via `config.yaml`

```yaml
persona:
  curiosity: 0.8
  warmth: 0.85
  directness: 0.7
  humor: 0.5
  formality: 0.3
  evolution_rate: 0.01  # How fast personality drifts from conversations
```

### Via Conversation

```
You: "Emily, be more direct and less formal from now on"
Emily: "You got it. I'll keep things straight and casual."
```

---

## 8. Teaching Skills

**Tell Emily how to do things, and she saves it as a skill.**

### Teach a Workflow

```
You:   "When I say 'morning report', I want you to:
        1. Check my calendar
        2. Summarize unread emails
        3. Give me the weather
        4. List today's tasks"
Emily: "Got it! I've saved 'morning report' as a skill."
```

Skills are stored in **procedural memory** (`data/procedural.json` → `skill_library`).

### View Skills

```bash
python -c "
import json
data = json.load(open('data/procedural.json'))
for skill in data.get('skill_library', []):
    print(f\"  {skill['name']}: {skill['description']}\")
"
```

---

## Training Schedule (Automatic)

Emily's self-improvement runs on a schedule:

| System | Trigger | Frequency |
|--------|---------|-----------|
| Interaction logging | Every turn | Immediate |
| Memory consolidation | End of session | Per session |
| RAG ingestion | File dropped in `knowledge/` | Real-time |
| Performance tracking | Every LLM/RAG call | Continuous |
| Prompt evolution | After N samples | ~Every 10 sessions |
| Reflection | Idle for 10+ minutes | Automatic |
| Capability gap review | Idle cycle | Periodic |
| Self-improvement cycle | Idle cycle | Every 30 min idle |

---

## Summary: How to Make Emily Smarter

| Action | Effect | Effort |
|--------|--------|--------|
| **Talk to her daily** | Builds episodic + semantic memory | Zero |
| **Drop files in `knowledge/`** | Expands knowledge base | Drag & drop |
| **Correct mistakes** | Improves accuracy | Say "that's wrong" |
| **Rate responses** | Evolves prompts + RAG quality | 👍 or 👎 |
| **Teach workflows** | Builds skill library | One-time |
| **Tune persona** | Adjusts personality | Edit one file |
| **Let her idle** | Self-reflection and optimization | Do nothing |

**The best training is simply using Emily every day.** She learns from every interaction automatically.
