# Emily's AI Models & Multilingual Capabilities

**Quick Answer:** Yes! Emily is **highly multilingual** — her text models support **119 languages** natively.

---

## 🤖 Models Emily Uses

Emily uses a **multi-tier model fleet** for different tasks. Here's the complete breakdown:

### 📝 Text Generation Models (Multilingual)

| Tier | Model | Languages | Use Case | VRAM |
|------|-------|-----------|----------|------|
| **nano** | JOSIEFIED-Qwen3:8b | **119 languages** | Fast routing, classification | ~5 GB |
| **voice_fast** | JOSIEFIED-Qwen3:8b | **119 languages** | Voice responses (<1 s) | ~5 GB |
| **fast** | JOSIEFIED-Qwen3:14b | **119 languages** | Standard conversation | ~9 GB |
| **smart** | Qwen3.5-abliterated:27b | **119 languages** | Complex tasks, planning | ~17 GB |
| **reasoning** | Qwen3.5-abliterated:27b | **119 languages** | Math, logic, chain-of-thought | ~17 GB |
| **cloud_best** | claude-opus-4-6 | **English-primary** | Reflection, agents, planning | cloud |
| **cloud_fast** | claude-sonnet-4-6 | **English-primary** | Fast cloud with thinking | cloud |

> **JOSIEFIED** = abliterated + fine-tuned to preserve tool-use and instruction-following.
> Cloud tiers require `ANTHROPIC_API_KEY` and send data to Anthropic's servers.

### 👁️ Vision Model

| Model | Purpose | Languages | VRAM |
|-------|---------|-----------|------|
| **MiniCPM-V 2.6** | Screen capture + webcam understanding, OCR | Multilingual | ~8 GB |

### 🔍 Embedding & Retrieval

| Model | Purpose | Languages | Size |
|-------|---------|-----------|------|
| **BGE-M3** | Document embedding (RAG) | **Multilingual** | ~2 GB |
| **BGE-reranker-v2-m3** | Search result reranking | **Multilingual** | ~1 GB |

### 🎤 Speech-to-Text (STT)

| Model | Purpose | Languages | Notes |
|-------|---------|-----------|-------|
| **Faster-Whisper large-v3-turbo** | Voice transcription | **99 languages** | ~50ms latency, CUDA optimized |

### 🔊 Text-to-Speech (TTS)

| Model | Purpose | Languages | Latency |
|-------|---------|-----------|---------|
| **Kokoro** (primary) | Voice synthesis | English (multi-accent) | <50ms |
| **CSM-1B** (quality) | High-quality speech | English | 200ms |
| **XTTS v2** (cloning) | Voice cloning | **13 languages** | 200ms |

---

## 🌍 Multilingual Support Summary

### ✅ **119 Languages** (Text Understanding & Generation)

Emily's **Qwen3** text models (nano, voice_fast, fast tiers) support **119 languages** including:

**Major Languages:**
- English, Spanish, French, German, Italian, Portuguese
- Chinese (Simplified & Traditional), Japanese, Korean
- Arabic, Russian, Hindi, Bengali, Turkish
- Dutch, Polish, Swedish, Danish, Norwegian
- ...and **100+ more**

**Language Families Covered:**
- Indo-European (Romance, Germanic, Slavic, Indo-Aryan)
- Sino-Tibetan (Chinese, Tibetan, Burmese)
- Afro-Asiatic (Arabic, Hebrew, Amharic)
- Japonic, Koreanic, Turkic, Austronesian, and more

### ✅ **99 Languages** (Speech Recognition)

Faster-Whisper large-v3-turbo recognizes spoken language in **99 languages**, including all major world languages.

### ✅ **Multilingual** (Vision)

MiniCPM-V can read and understand text in **multiple languages** from screenshots and camera feeds (OCR in many scripts).

### ✅ **Multilingual** (Embeddings)

BGE-M3 embeddings work across **many languages** for document retrieval and semantic search.

### ⚠️ **English-focused** (Text-to-Speech)

Current TTS engines are **primarily English** with limited multilingual support:
- **Kokoro**: English (multiple accents)
- **CSM-1B**: English
- **XTTS v2**: 13 languages (English, Spanish, French, German, Italian, Portuguese, Polish, Turkish, Russian, Dutch, Czech, Arabic, Chinese)

---

## 🔄 How Emily Handles Multiple Languages

### Automatic Language Detection

Emily **automatically detects** the language you're using:

1. **Text input** (chat): Qwen3 models understand and respond in the same language you use
2. **Voice input**: Whisper STT detects language automatically (or you can set it in config)
3. **Documents**: BGE-M3 embeddings work cross-lingually for multilingual RAG

### Configuration

**Default language** (STT): Set in `config.yaml`:

```yaml
stt:
  language: "en"  # Change to: "es", "fr", "de", "zh", "ja", etc.
  # Or set to null for auto-detection
```

**Response language**: Emily responds in the language you use. No configuration needed!

### Example Multilingual Conversations

**Spanish:**
```
You: "¿Cómo estás hoy, Emily?"
Emily: "¡Estoy muy bien, gracias por preguntar! ¿En qué puedo ayudarte?"
```

**French:**
```
You: "Peux-tu m'aider avec quelque chose?"
Emily: "Bien sûr! Je serais ravie de vous aider. Qu'avez-vous besoin?"
```

**Chinese:**
```
You: "你好，Emily。你能帮我吗？"
Emily: "你好！当然可以，我很乐意帮助你。你需要什么帮助？"
```

**Japanese:**
```
You: "エミリー、手伝ってくれますか？"
Emily: "もちろんです！喜んでお手伝いします。何が必要ですか？"
```

---

## 🚀 Performance by Language

### Tier 1 Languages (Best Performance)

Emily performs best in:
- **English** (most training data, all capabilities)
- **Chinese** (Qwen models are Chinese-first)
- **Spanish, French, German, Russian, Japanese, Korean**

### Tier 2 Languages (Strong Performance)

Good performance in:
- Most European languages
- Major Asian languages
- Arabic, Hebrew, Turkish

### Tier 3 Languages (Basic Support)

Basic support for:
- Less common languages
- Low-resource languages

**Note**: All 119 languages are supported, but quality may vary based on training data availability.

---

## 🔧 Technical Details

### Model Architecture

**Qwen3 / Qwen3.5 Series:**
- Trained on **36 trillion tokens**
- **256K context window** (Qwen3.5-27B)
- **128K context window** (Qwen3-14B)
- **32K context window** (Qwen3-8B)
- Hybrid thinking/non-thinking mode (controlled per-tier via `enable_thinking`)
- Multilingual from the ground up

**Why Qwen3/3.5 for Multilingual?**
1. Alibaba's training data includes massive multilingual corpora
2. Better multilingual tokenization than Western-first models
3. Strong performance on non-English benchmarks
4. Native code-mixing support (switching languages mid-sentence)

**JOSIEFIED Variants:**
- Abliterated (refusals removed) + fine-tuned to preserve tool-use and structured output
- Used for `nano`, `voice_fast`, and `fast` tiers where instruction-following precision matters

### Backend Infrastructure

```
┌─────────────────────────────────────────────────────────┐
│  Text Generation: Ollama (all local tiers)              │
│    • JOSIEFIED-Qwen3:8b  (nano, voice_fast)             │
│    • JOSIEFIED-Qwen3:14b (fast)                         │
│    • Qwen3.5-abliterated:27b (smart, reasoning)         │
│    • All served via Ollama — no ExLlamaV2 required      │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Vision & Embedding: Ollama                              │
│    • MiniCPM-V (multilingual vision)                     │
│    • BGE-M3 (multilingual embeddings)                   │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Cloud (optional): Anthropic API                         │
│    • Claude Opus 4.6  (cloud_best — agents, planning)   │
│    • Claude Sonnet 4.6 (cloud_fast — fast with thinking) │
│    • Requires ANTHROPIC_API_KEY env var                  │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Voice: Faster-Whisper + Kokoro                          │
│    • Whisper large-v3-turbo (99 languages STT)          │
│    • Kokoro af_heart (English TTS, local)                │
└─────────────────────────────────────────────────────────┘
```

---

## 📊 Language Capabilities Comparison

| Capability | Languages | Notes |
|------------|-----------|-------|
| **Chat/Conversation** | 119 | Full conversational AI in any supported language |
| **Voice Recognition** | 99 | Whisper STT with automatic language detection |
| **Voice Synthesis** | 1 primary (English) | 13 with XTTS v2, English-focused by default |
| **Document Understanding** | 119+ | RAG/knowledge base works cross-lingually |
| **Vision/OCR** | Many | Can read text in multiple scripts |
| **Code Understanding** | Universal | Programming languages (Python, JS, etc.) work in all locales |

---

## 🔮 Future Multilingual Enhancements

Potential improvements (not yet implemented):

1. **Multilingual TTS**: Add models like VALL-E X, YourTTS, or MMS for broader language support
2. **Language-specific optimizations**: Fine-tune Qwen3 on specific language pairs
3. **Code-mixing**: Better handling of multilingual conversations (switching mid-sentence)
4. **Regional accents**: More TTS voices for different English accents and languages

---

## 💡 Use Cases

### 1. International Users
Emily works natively in your language — no English required!

### 2. Language Learning
Practice conversation in any of 119 languages with immediate feedback.

### 3. Translation & Localization
Use Emily to translate text, understand foreign documents, or help with localization.

### 4. Multilingual Document Processing
Ingest documents in any language and query them cross-lingually.

### 5. Global Development
Code and converse in your native language while working on international projects.

---

## 📝 Quick Reference

**Change STT Language:**
```yaml
# config.yaml
stt:
  language: "es"  # Spanish
  # Or null for auto-detect
```

**Test Multilingual:**
```bash
# Start Emily
./scripts/start-emily.sh gui

# Try in your language:
# - Chat: Type in any of 119 languages
# - Voice: Speak in any of 99 languages
# - Documents: Add files in any language to knowledge/
```

**Check Model Languages:**
```bash
# List all Ollama models
ollama list

# Qwen3/3.5 models support 119 languages
# Whisper supports 99 languages
# Check: https://github.com/openai/whisper#available-models-and-languages
```

---

## 🎯 Summary

**✅ YES, Emily is highly multilingual!**

- **119 languages** for text understanding and generation
- **99 languages** for speech recognition
- **Multilingual** vision and document processing
- **Native support** — no translation layer, direct understanding
- **All local** — zero cloud dependency

Emily speaks your language! 🌍

---

**Last Updated**: March 1, 2026
**Version**: Emily 1.0
