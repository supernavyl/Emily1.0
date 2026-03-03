# TabbyAPI Integration — Quick Reference

Emily now uses **TabbyAPI** (ExLlamaV2) for all text generation with fully **abliterated** models.

---

## What Changed

### Before (Ollama-only)
- nano: Qwen3-4B (Ollama/llamacpp)
- fast: Qwen3-14B (Ollama)
- smart: QwQ-32B (Ollama)

### After (TabbyAPI + Ollama hybrid)
- **nano/voice_fast/fast**: Qwen2.5-14B-Instruct-abliterated (**TabbyAPI EXL2**)
- **smart/reasoning**: QwQ-32B-abliterated (**TabbyAPI EXL2**)
- **vision**: MiniCPM-V (Ollama — unchanged)
- **embedding**: BGE-M3 (Ollama — unchanged)

---

## Setup Checklist

- [ ] Install TabbyAPI → `~/TabbyAPI`
- [ ] Download abliterated EXL2 models → `~/models/tabby/`
    - [ ] Qwen2.5-14B-Instruct-abliterated (4.65bpw, ~8.5 GB VRAM)
    - [ ] QwQ-32B-abliterated (4.0bpw, ~17 GB VRAM)
- [ ] Configure `~/TabbyAPI/config.yml` (set model_dir, disable auth)
- [ ] Verify setup: `./scripts/verify-tabbyapi.sh`
- [ ] Start TabbyAPI: `cd ~/TabbyAPI && source venv/bin/activate && python main.py --model Qwen2.5-14B-Instruct-abliterated`
- [ ] Start Emily: `./scripts/start-emily.sh`

---

## Quick Commands

### Check TabbyAPI status
```bash
curl -s http://localhost:5000/v1/models | jq
```

### Load a different model (hot-swap)
```bash
# Switch to QwQ-32B for reasoning tasks
curl -X POST http://localhost:5000/v1/model/load \
  -H "Content-Type: application/json" \
  -d '{"name": "QwQ-32B-abliterated"}'

# Switch back to Qwen2.5-14B for standard conversation
curl -X POST http://localhost:5000/v1/model/load \
  -H "Content-Type: application/json" \
  -d '{"name": "Qwen2.5-14B-Instruct-abliterated"}'
```

### Start TabbyAPI (manual)
```bash
cd ~/TabbyAPI
source venv/bin/activate
python main.py --model Qwen2.5-14B-Instruct-abliterated
```

### Start entire Emily stack
```bash
cd ~/Emily1.0
./scripts/start-emily.sh all
```

### Verify Emily can reach TabbyAPI
```bash
cd ~/Emily1.0
python -c "from llm.fleet import LLMFleet; import asyncio; from config import get_config; asyncio.run(LLMFleet(get_config().llm).startup())"
```

---

## Troubleshooting

### TabbyAPI won't start
- Check logs: `tail -f ~/TabbyAPI/logs/tabby.log` (or `~/Emily1.0/logs/tabbyapi.log` if started via script)
- Verify CUDA: `nvidia-smi`
- Check model files exist: `ls ~/models/tabby/Qwen2.5-14B-Instruct-abliterated/*.safetensors`

### Connection refused
- TabbyAPI not running → start it manually or via `./scripts/start-emily.sh infra`
- Port 5000 in use → `sudo lsof -i :5000` and kill conflicting process

### Model not found
- Directory names must **exactly match** config.yaml model names
- Case-sensitive: `Qwen2.5-14B-Instruct-abliterated` (not `qwen2.5-14b-instruct-abliterated`)
- TabbyAPI derives model IDs from folder names in `model_dir`

### Emily falls back to Ollama
- Check TabbyAPI is running: `curl http://localhost:5000/v1/models`
- Check `config.yaml` → `llm.tier_backend.*` → all set to `"tabbyapi"` (except vision/embedding)
- Check Emily logs: `tail -f logs/emily.log | grep -i tabby`

---

## Files Modified

| File | Change |
|------|--------|
| `config.yaml` | Updated `llm.models.*` and `llm.tier_backend.*` to use TabbyAPI |
| `scripts/start-emily.sh` | Added TabbyAPI startup logic |
| `README.md` | Updated architecture diagram, model tiers table, quick start |
| `docs/TABBYAPI_SETUP.md` | **New** — full TabbyAPI installation guide |
| `scripts/verify-tabbyapi.sh` | **New** — verification script |

---

## Why Abliterated Models?

- **No refusals**: Alignment layers removed — Emily can reason about any topic without "I cannot help with that" responses
- **Transparent reasoning**: Native `<think>...</think>` blocks expose chain-of-thought reasoning
- **Lower latency**: No alignment tax overhead during inference
- **Authenticity**: Emily's personality comes from her prompt engineering, not hardcoded refusal patterns

---

## Documentation

- **Full setup guide**: [docs/TABBYAPI_SETUP.md](TABBYAPI_SETUP.md)
- **System architecture**: [ARCHITECTURE.md](../ARCHITECTURE.md)
- **Model routing logic**: `llm/router.py` + `llm/fleet.py`
- **TabbyAPI client**: `llm/tabbyapi_client.py`

---

## Next Steps

1. **Install TabbyAPI** → See [TABBYAPI_SETUP.md](TABBYAPI_SETUP.md)
2. **Download models** → Use HuggingFace CLI
3. **Verify setup** → Run `./scripts/verify-tabbyapi.sh`
4. **Start Emily** → Run `./scripts/start-emily.sh`
5. **Test voice conversation** → Say "Hey Emily" and ask a complex question

**Recommended first test query:**
> "Explain the trolley problem and analyze it from multiple ethical frameworks, showing your reasoning step by step."

Watch for `<think>...</think>` blocks in the response — that's Emily using the abliterated model's native CoT.

---

Ready? Run the verification script:

```bash
./scripts/verify-tabbyapi.sh
```
