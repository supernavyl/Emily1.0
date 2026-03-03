# Run Everything (Emily Full Stack)

This guide is the fastest way to run the entire Emily system on your machine.

## What "everything" includes

- Docker infra: Qdrant, SearXNG, Prometheus, Grafana, Jaeger
- TabbyAPI (text + voice inference backend)
- Ollama (vision + embeddings)
- FastAPI server (`api.app`)
- Emily core voice runtime (`main.py --no-gui`)

## 0) One-time setup

```bash
cd ~/Emily1.0
uv sync --extra gpu-cuda --extra dev --extra desktop
cp .env.example .env
```

Optional but recommended:

```bash
.venv/bin/python -m spacy download en_core_web_sm
```

## 1) Start everything (recommended)

From the repo root:

```bash
./scripts/start-emily.sh
```

This starts services in dependency order and prints health status.

## 2) Check status

```bash
./scripts/start-emily.sh status
```

Useful endpoints:

- API dashboard: `http://localhost:8080`
- API docs: `http://localhost:8080/docs`
- Voice dashboard: `http://localhost:8080/voice-dashboard`
- Grafana: `http://localhost:3000`
- Prometheus: `http://localhost:9090`
- Jaeger: `http://localhost:16686`
- Qdrant: `http://localhost:6333/dashboard`

## 3) Stop everything

```bash
./scripts/start-emily.sh stop
```

## Run only specific parts

```bash
./scripts/start-emily.sh infra   # docker + tabbyapi + ollama
./scripts/start-emily.sh api     # api only
./scripts/start-emily.sh core    # voice core only
./scripts/start-emily.sh gui     # core with GUI dashboards
./scripts/start-emily.sh chat    # desktop chat app
./scripts/start-emily.sh web     # react web frontend
```

If `core` or `gui` is already running, startup now exits safely with
an "already running" message instead of crashing on bus ports.

## If something fails

1. Check health:
   ```bash
   ./scripts/start-emily.sh status
   ```
2. Check TabbyAPI:
   ```bash
   ./scripts/verify-tabbyapi.sh
   ```
3. Check GPU + model backends:
   ```bash
   nvidia-smi
   ollama list
   curl -s http://localhost:5000/v1/models | jq
   ```
4. Restart cleanly:
   ```bash
   ./scripts/start-emily.sh stop
   ./scripts/start-emily.sh
   ```
