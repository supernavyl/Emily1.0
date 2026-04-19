# Baseline snapshot — 2026-04-19T06:21:42Z

## GPU
index, name, memory.used [MiB], memory.total [MiB]
0, NVIDIA GeForce RTX 4090, 18061 MiB, 24564 MiB
1, NVIDIA GeForce RTX 3060, 186 MiB, 12288 MiB

## Ollama models
NAME                                                 ID              SIZE      MODIFIED    
qwen3-embedding:8b                                   64b933495768    4.7 GB    2 days ago     
glm-4.7-flash:latest                                 d1a8a26252f1    19 GB     11 days ago    
juilpark/gemma-4-31B-it-uncensored-heretic:q4_K_M    31611c6fd19f    18 GB     13 days ago    
huihui_ai/qwen3.5-abliterated:27b                    e9ff39f1ea00    17 GB     2 weeks ago    
huihui_ai/qwen3.5-abliterated:9b                     92a443adb124    6.6 GB    2 weeks ago    
goekdenizguelmez/JOSIEFIED-Qwen3:14b                 bc2c7a445286    9.0 GB    4 weeks ago    
minimax-m2.5:cloud                                   c0d5751c800f    -         6 weeks ago    
huihui_ai/qwen3-coder-abliterated:30b                3350697b83c3    18 GB     6 weeks ago    
huihui_ai/deepseek-r1-abliterated:32b                fb53b3296912    19 GB     6 weeks ago    
qwen3-coder-next:cloud                               aa626c11ae8d    -         7 weeks ago    
kimi-k2.5:cloud                                      6d1c3246c608    -         7 weeks ago    

## Current voice_fast tier (llm/fleet.py)
160:        "voice_fast": "Voice",
184:            "voice_fast",
322:                for tier in ("nano", "voice_fast", "fast", "smart", "reasoning", "embedding")
344:                "voice_fast",
382:            voice_model = self._config.models.nano or self._config.models.voice_fast
400:                for t in ("nano", "voice_fast", "fast", "smart", "reasoning")
931:            voice_mode: When True, biases toward VOICE_FAST for simple queries.

## Current TTS provider config (voice_engine/config.py)
44:    stt_device_index: int = Field(default=0, description="CUDA device index: 0=4090, 1=3060")
45:    stt_compute_type: str = Field(default="float16", description="STT compute type: 'float16', 'int8', 'int8_float16'")
56:    tts_provider: str = Field(default="kokoro", description="TTS provider (kokoro)")
57:    tts_voice: str = Field(default="af_nicole", description="Kokoro voice identifier")

## config.yaml voice_engine section
186:    model_name: "tts_models/multilingual/multi-dataset/xtts_v2"
228:voice_engine:
230:  # Provider selection (detailed config in .env — see voice_engine/config.py)
231:  stt_provider: "faster_whisper"
233:  tts_provider: "tiered"

## Python packages of interest
  qwen_tts: NOT INSTALLED
  kokoro: 0.9.4
  snac: 1.2.1
  llama_cpp: NOT INSTALLED
  faster_whisper: 1.2.1
  torch: 2.10.0+cu128

## Orpheus GGUF (dormant, kept as v2 fallback)
.rw-r--r-- 2.4G supernovyl  8 Mar 00:13 models/orpheus-3b-0.1-ft-q4_k_m.gguf

## Git HEAD
0a1b149c748965b0177d46c7e19bae8cdc800064
Branch: feat/emily-loop-integration
