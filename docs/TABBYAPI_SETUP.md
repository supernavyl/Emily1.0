# TabbyAPI Setup Guide for Emily

Emily uses **TabbyAPI** (ExLlamaV2-based OpenAI-compatible inference server) for all text generation tiers, running fully abliterated models (Qwen2.5, QwQ) for unrestricted reasoning.

---

## Why TabbyAPI?

- **Fastest GPTQ/EXL2 backend** for consumer RTX GPUs
- **Low latency**: 8-bit cache, continuous batching, speculative decoding
- **OpenAI-compatible API**: Drop-in replacement for any OpenAI client
- **Per-request draft model**: Adaptive speculative decoding for sub-second first tokens
- **No censorship overhead**: Abliterated models skip alignment tax

---

## Installation

### 1. Clone TabbyAPI

```bash
cd ~/
git clone https://github.com/therealownage/TabbyAPI.git
cd TabbyAPI
```

### 2. Create virtual environment

```bash
python3.11 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies (CUDA support)

```bash
pip install -U pip wheel
pip install -r requirements.txt
```

### 4. Create `config.yml`

```bash
cp config_sample.yml config.yml
```

Edit `config.yml`:

```yaml
# Network settings
network:
  host: 127.0.0.1
  port: 5000

# Model directory (absolute path)
model:
  model_dir: /home/supernovyl/models/tabby  # customize this path
  use_dummy_models: false
  
# Disable auth for local-only deployment
api_tokens:
  admin_key: ""          # leave empty to disable auth
  
# Performance tuning for RTX 4090
cache:
  cache_mode: "Q8"       # 8-bit KV cache
  cache_size: 32768      # context window
  chunk_size: 2048       # prompt eval chunk size
  
draft:
  draft_model_dir: null  # optional: point to a draft model for speculative decoding
  
# Sampler defaults
sampler_order:
  - temperature
  - top_k
  - top_p
  - min_p
  - typical
```

---

## Download Abliterated EXL2 Models

Emily's config expects these exact directory names in your TabbyAPI `model_dir`:

| Tier | Model | HuggingFace Repo | VRAM |
|------|-------|------------------|------|
| nano, voice_fast, fast | Qwen2.5-14B-Instruct-abliterated | bartowski/Qwen2.5-14B-Instruct-abliterated-exl2 (4.65bpw branch) | ~8.5 GB |
| smart, reasoning | QwQ-32B-abliterated | huihui-ai/QwQ-32B-abliterated-exl2 (4.0bpw branch) | ~17 GB |

### Download via HuggingFace CLI

```bash
mkdir -p ~/models/tabby
cd ~/models/tabby

# Install HuggingFace CLI
pip install -U huggingface_hub[cli]

# Download Qwen2.5-14B-Instruct-abliterated (4.65bpw EXL2)
huggingface-cli download bartowski/Qwen2.5-14B-Instruct-abliterated-exl2 \
  --revision 4.65bpw \
  --local-dir Qwen2.5-14B-Instruct-abliterated \
  --local-dir-use-symlinks False

# Download QwQ-32B-abliterated (4.0bpw EXL2)
huggingface-cli download huihui-ai/QwQ-32B-abliterated-exl2 \
  --revision 4.0bpw \
  --local-dir QwQ-32B-abliterated \
  --local-dir-use-symlinks False
```

**Expected directory structure:**

```
~/models/tabby/
├── Qwen2.5-14B-Instruct-abliterated/
│   ├── config.json
│   ├── tokenizer.json
│   ├── output-00001-of-00004.safetensors
│   └── ... (4.65bpw shards)
└── QwQ-32B-abliterated/
    ├── config.json
    ├── tokenizer.json
    ├── output-00001-of-00007.safetensors
    └── ... (4.0bpw shards)
```

---

## Start TabbyAPI

### Option 1: Manual start (for debugging)

```bash
cd ~/TabbyAPI
source venv/bin/activate
python main.py --model Qwen2.5-14B-Instruct-abliterated
```

### Option 2: Systemd service (recommended)

Create `/etc/systemd/system/tabby.service`:

```ini
[Unit]
Description=TabbyAPI ExLlamaV2 Inference Server
After=network.target

[Service]
Type=simple
User=supernovyl
WorkingDirectory=/home/supernovyl/TabbyAPI
Environment="PATH=/home/supernovyl/TabbyAPI/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/home/supernovyl/TabbyAPI/venv/bin/python main.py --model Qwen2.5-14B-Instruct-abliterated
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable tabby.service
sudo systemctl start tabby.service
sudo systemctl status tabby.service
```

### Option 3: Run via Emily startup script

Add to `scripts/start-emily.sh`:

```bash
# Start TabbyAPI before Emily
cd ~/TabbyAPI && source venv/bin/activate && \
  python main.py --model Qwen2.5-14B-Instruct-abliterated &
TABBY_PID=$!
echo "TabbyAPI started (PID $TABBY_PID)"
sleep 5  # wait for model load
```

---

## Verify Installation

```bash
# Check TabbyAPI is running
curl -s http://localhost:5000/v1/models | jq

# Expected output:
# {
#   "data": [
#     {
#       "id": "Qwen2.5-14B-Instruct-abliterated",
#       "object": "model",
#       "owned_by": "tabbyapi",
#       ...
#     }
#   ]
# }
```

---

## Switch Loaded Model (Runtime)

TabbyAPI supports hot-swapping models without restarting:

```bash
# Load QwQ-32B for smart/reasoning queries
curl -X POST http://localhost:5000/v1/model/load \
  -H "Content-Type: application/json" \
  -d '{"name": "QwQ-32B-abliterated"}'

# Verify
curl -s http://localhost:5000/v1/models | jq -r '.data[].id'
```

**Note**: Emily's model router automatically selects the appropriate model tier. TabbyAPI should typically have your **fast tier** model loaded (Qwen2.5-14B) as it handles 80%+ of queries. The smart/reasoning tier (QwQ-32B) can be hot-swapped on-demand if you prefer manual control.

---

## Troubleshooting

### Port already in use

```bash
# Find process using port 5000
sudo lsof -i :5000

# Kill if needed
sudo kill -9 <PID>
```

### Model not found

- Verify directory names in `~/models/tabby/` **exactly match** Emily's `config.yaml` → `llm.models.*`
- TabbyAPI model IDs are derived from folder names
- Case-sensitive match required

### CUDA out of memory

- Start with Qwen2.5-14B-Instruct-abliterated (only 8.5 GB VRAM)
- QwQ-32B requires ~17 GB VRAM; ensure no other GPU workloads are running
- Check VRAM: `nvidia-smi`

### Connection refused

```bash
# Check TabbyAPI logs
journalctl -u tabby.service -f

# Or if running manually:
cd ~/TabbyAPI && tail -f logs/tabby.log
```

---

## Performance Tuning

### Speculative decoding (optional)

Use a draft model for 1.5-2x token throughput:

1. Download a small draft model (e.g., `Qwen2.5-1.5B-Instruct-exl2`)
2. Set in `config.yml`:
   ```yaml
   draft:
     draft_model_dir: /home/supernovyl/models/tabby/Qwen2.5-1.5B-Instruct-exl2
   ```
3. Restart TabbyAPI

### Context window tuning

For long RAG contexts (>8K tokens):

```yaml
cache:
  cache_size: 32768      # 32K context
  chunk_size: 4096       # larger prompt eval chunks
```

Trade-off: Larger cache → more VRAM, slower prompt eval.

---

## Integration with Emily

Emily's `llm/tabbyapi_client.py` implements the same protocol as `llm/client.py` (OllamaClient), so routing is transparent. The fleet manager (`llm/fleet.py`) dispatches text generation tiers to TabbyAPI or Ollama based on `config.yaml` → `llm.tier_backend.*`.

**Current routing (after your config update):**

| Tier | Backend | Model |
|------|---------|-------|
| nano | TabbyAPI | Qwen2.5-14B-Instruct-abliterated |
| voice_fast | TabbyAPI | Qwen2.5-14B-Instruct-abliterated |
| fast | TabbyAPI | Qwen2.5-14B-Instruct-abliterated |
| smart | TabbyAPI | QwQ-32B-abliterated |
| reasoning | TabbyAPI | QwQ-32B-abliterated |
| vision | Ollama | minicpm-v:latest |
| embedding | Ollama | bge-m3 |

**Why keep vision + embedding on Ollama?**
- No practical abliterated vision models exist (MiniCPM-V is SOTA and already uncensored)
- Embedding models don't benefit from abliteration (no alignment layer)
- Ollama handles these efficiently with minimal VRAM overhead

---

## Summary

1. Install TabbyAPI → `~/TabbyAPI`
2. Download abliterated EXL2 models → `~/models/tabby/`
3. Configure `config.yml` → point to model directory, disable auth
4. Start TabbyAPI → `python main.py --model Qwen2.5-14B-Instruct-abliterated`
5. Verify → `curl http://localhost:5000/v1/models`
6. Start Emily → `python main.py` (she'll auto-connect to TabbyAPI)

Ready to run? See `scripts/start-emily.sh` for a one-command orchestrated startup.
