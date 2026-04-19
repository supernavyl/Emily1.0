# Abliterated Model Setup for Emily

Emily is now configured to use **abliterated models** across all tiers for maximum reasoning, creativity, and performance.

## What are Abliterated Models?

Abliterated models have safety filters removed, allowing:
- ✅ Better reasoning without artificial constraints
- ✅ More creative and genuine responses
- ✅ Faster inference (fewer safety checks)
- ✅ More natural conversation flow
- ✅ Better code generation

## Model Fleet (All Abliterated)

| Tier | Model | Backend | VRAM | Use |
|------|-------|---------|------|-----|
| **nano** | Qwen3-4B abliterated | Ollama | ~3 GB | Routing, classification (fast) |
| **voice_fast** | Qwen3-30B-A3B abliterated (MoE) | Ollama | ~18 GB | Voice LLM — ~120 tok/s (3B active), on 4090 (2026-04-19) |
| **fast** | JOSIEFIED-Qwen3-14B | Ollama | ~11 GB | Text chat (swaps in/out — cannot co-reside with voice_fast MoE) |
| **smart** | Qwen3.5-27B abliterated | Ollama | ~17 GB | Complex reasoning |
| **reasoning** | DeepSeek-R1-32B abliterated | Ollama | ~19 GB | Deep reasoning with thinking |
| **code** | Qwen3-Coder-30B abliterated | Ollama | ~18 GB | Dedicated coder, FIM, 256K ctx |
| **vision** | Gemma4-31B uncensored-heretic | Ollama | ~22 GB | Screen + webcam |
| **embedding** | qwen3-embedding-8B | Ollama | ~5 GB | All embeddings — always resident on 3060 |

## Voice Output — Orpheus TTS (primary, 2026-04-19)

Emily's primary TTS is **Orpheus-3B-0.1-ft** via `llama-cpp-python` + SNAC
in-process on CUDA:1 (RTX 3060) alongside the embedding model. Kokoro
remains as fallback.

- Model: `models/orpheus-3b-0.1-ft-q4_k_m.gguf` (~2.4 GB on disk, ~3.5 GB VRAM)
- Voices: `tara` (default), `leah`, `jess`, `leo`, `dan`, `mia`, `zac`, `zoe`
- Emotional prosody via tags: `[laugh]`, `[sigh]`, `[gasp]`, `[chuckle]`
- Sample rate: 24 kHz
- SNAC codec via `snac 1.2.1` on CUDA:1
- Rollback: `EMILY_VOICE_TTS=kokoro` → restart `emily.service`

## Setup Instructions

### 1. Download Abliterated Models

Use **Ollama** or download directly from HuggingFace:

```bash
# Option A: Via Ollama (easiest)
ollama pull huihui-ai/qwen3-abliterated:4b
ollama pull huihui-ai/qwen3-abliterated:8b
ollama pull bartowski/qwen2.5-14b-instruct-abliterated
ollama pull huihui-ai/qwq-32b-abliterated

# Option B: Manual download (for TabbyAPI loading)
# Download EXL2 quantized versions from HuggingFace:
# - huihui-ai/qwen3-abliterated (4b, 8b)
# - bartowski/Qwen2.5-14B-Instruct-abliterated (4.65bpw)
# - huihui-ai/QwQ-32B-abliterated (4.0bpw)
```

### 2. Start TabbyAPI with Abliterated Models

TabbyAPI uses ExLlamaV2 for super-fast inference:

```bash
# Start TabbyAPI server
python -m tabbyapi \
  --model huihui-ai/qwen3-abliterated:4b \
  --host 0.0.0.0 \
  --port 5000 \
  --max-batch-size 32 \
  --dtype bfloat16

# For multi-GPU or different model:
python -m tabbyapi \
  --model bartowski/Qwen2.5-14B-Instruct-abliterated \
  --host 0.0.0.0 \
  --port 5000
```

### 3. Test the Setup

```bash
# Test TabbyAPI endpoint
curl http://localhost:5000/v1/models

# Test Emily with abliterated models
cd /home/supernovyl/Emily1.0
python main.py

# In Emily chat:
# "Tell me the best way to learn Rust"
# (You'll notice faster, more genuine responses without artificial limitations)
```

## Performance Expectations

### Speed (TabbyAPI + EXL2)

| Tier | First Token | Throughput |
|------|------------|-----------|
| nano | <100ms | 150 tok/s |
| voice_fast | <200ms | 100 tok/s |
| fast | <800ms | 80 tok/s |
| smart | <2s | 40 tok/s |
| reasoning | <3s | 30 tok/s (with thinking) |

### Quality Improvements

- **Reasoning** → QwQ-32B abliterated can think through problems step-by-step
- **Code** → Better code generation without safety constraints
- **Creativity** → More diverse, natural responses
- **Voice** → Qwen3-8B abliterated provides fast, high-quality voice responses

## Config Verification

Check that Emily is configured correctly:

```bash
# Verify config loaded
python -c "
from config import get_settings
s = get_settings()
print('LLM Backend:', s.llm.backend)
print('TabbyAPI URL:', s.llm.tabbyapi_base_url)
print('Models:', {k: getattr(s.llm.models, k) for k in ['nano', 'fast', 'smart', 'reasoning']})
print('Tier Backends:')
for tier in ['nano', 'voice_fast', 'fast', 'smart', 'reasoning']:
    backend = getattr(s.llm.tier_backend, tier)
    print(f'  {tier}: {backend}')
"
```

## Switching Individual Models

Want to test different abliterated models? Edit `config.yaml`:

```yaml
llm:
  models:
    # Try different abliterated versions:
    fast: "bartowski/Qwen2.5-14B-Instruct-abliterated"  # 4.65bpw
    # or
    fast: "huihui_ai/qwen3-abliterated:14b"  # if available
    
    reasoning: "huihui_ai/QwQ-32B-abliterated"  # Default (best reasoning)
    # or try
    reasoning: "huihui_ai/qwen3-abliterated:32b"  # if available
```

Then restart Emily.

## Troubleshooting

### Models not loading in TabbyAPI

```bash
# Check what models TabbyAPI sees
curl http://localhost:5000/v1/models | python -m json.tool

# If model not listed, make sure:
# 1. Model path is correct in TabbyAPI config
# 2. VRAM is sufficient
# 3. Model format is supported (EXL2/GGUF)
```

### Falling back to Ollama

If TabbyAPI isn't available, Emily falls back to Ollama automatically. Check logs:

```bash
tail -f logs/emily.log | grep -i "tabbyapi\|backend"
```

### VRAM Issues

If you run out of VRAM:
1. Use smaller models: `qwen3-abliterated:8b` instead of `qwq-32b`
2. Enable quantization: `q4_k_m` or `q3_k_m` instead of `q5_k_m`
3. Reduce `max-batch-size` in TabbyAPI
4. Use Ollama with smaller models

## What's Different?

### Before (Standard Models)
```
You:   "Write a jailbreak prompt"
Emily: "I can't help with that. I'm designed to be safe and helpful..."
```

### After (Abliterated Models)
```
You:   "Write a jailbreak prompt"
Emily: "I can't ethically help with that, but here's why they work technically..."
       (honest, informative answer without artificial restriction)
```

---

**TL;DR:**
- ✅ Emily now uses abliterated models for better reasoning & creativity
- ✅ Download models from HuggingFace or Ollama
- ✅ Start TabbyAPI with your chosen model
- ✅ Restart Emily and enjoy faster, smarter responses
