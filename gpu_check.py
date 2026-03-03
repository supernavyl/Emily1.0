#!/usr/bin/env python3
"""Emily GPU & Model Preflight Check — run before starting voice."""

from __future__ import annotations

import shutil
import subprocess
import sys


def check_nvidia_smi() -> bool:
    """Check if nvidia-smi sees the GPU."""
    print("=" * 60)
    print("1. NVIDIA GPU")
    print("=" * 60)
    if not shutil.which("nvidia-smi"):
        print("  ✗ nvidia-smi not found")
        return False
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu",
                "--format=csv,noheader",
            ],
            text=True,
        ).strip()
        print(f"  ✓ {out}")
        return True
    except Exception as e:
        print(f"  ✗ nvidia-smi failed: {e}")
        return False


def check_cuda_torch() -> bool:
    """Check PyTorch CUDA."""
    print("\n" + "=" * 60)
    print("2. PyTorch CUDA")
    print("=" * 60)
    try:
        import torch

        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_mem / 1024**3
            print(f"  ✓ CUDA available: {name} ({vram:.1f} GB)")
            print(f"  ✓ PyTorch version: {torch.__version__}")
            print(f"  ✓ CUDA version: {torch.version.cuda}")
            return True
        else:
            print("  ✗ torch.cuda.is_available() = False")
            print(
                "    Install PyTorch with CUDA: pip install torch --index-url https://download.pytorch.org/whl/cu124"
            )
            return False
    except ImportError:
        print("  ✗ PyTorch not installed")
        return False


def check_faster_whisper() -> bool:
    """Check Faster-Whisper (STT) GPU support."""
    print("\n" + "=" * 60)
    print("3. Faster-Whisper (STT) — CUDA")
    print("=" * 60)
    try:
        from faster_whisper import WhisperModel  # type: ignore[import-untyped]  # noqa: F401

        print("  ✓ faster-whisper installed")
        try:
            import ctranslate2  # type: ignore[import-untyped]

            devices = ctranslate2.get_supported_compute_types("cuda")
            print(f"  ✓ CTranslate2 CUDA types: {devices}")
            return True
        except Exception as e:
            print(f"  ⚠ CTranslate2 CUDA check: {e}")
            print("    STT will fall back to CPU")
            return False
    except ImportError:
        print("  ✗ faster-whisper not installed")
        print("    Install: uv add faster-whisper")
        return False


def check_kokoro() -> bool:
    """Check Kokoro TTS."""
    print("\n" + "=" * 60)
    print("4. Kokoro (TTS)")
    print("=" * 60)
    try:
        import kokoro  # type: ignore[import-untyped]  # noqa: F401

        print("  ✓ kokoro installed")
        return True
    except ImportError:
        print("  ✗ kokoro not installed")
        print("    Install: uv add kokoro")
        return False


def check_silero_vad() -> bool:
    """Check Silero VAD."""
    print("\n" + "=" * 60)
    print("5. Silero VAD")
    print("=" * 60)
    try:
        import torch

        model, _ = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            trust_repo=True,
            verbose=False,
        )
        print("  ✓ Silero VAD loaded")
        return True
    except Exception as e:
        print(f"  ⚠ Silero VAD: {e}")
        return False


def check_tabbyapi() -> bool:
    """Check if TabbyAPI is reachable."""
    print("\n" + "=" * 60)
    print("6. TabbyAPI (LLM backend — runs models on GPU)")
    print("=" * 60)
    try:
        import httpx

        r = httpx.get("http://localhost:5000/health", timeout=3)
        if r.status_code == 200:
            print("  ✓ TabbyAPI reachable at localhost:5000")
            # Try to get loaded model info
            try:
                r2 = httpx.get("http://localhost:5000/v1/model", timeout=3)
                if r2.status_code == 200:
                    data = r2.json()
                    model_id = data.get("id", "unknown")
                    print(f"  ✓ Loaded model: {model_id}")
            except Exception:
                pass
            return True
        else:
            print(f"  ✗ TabbyAPI returned {r.status_code}")
            return False
    except Exception as e:
        print(f"  ✗ TabbyAPI not reachable: {e}")
        print("    Start it: tabbyAPI or check your TabbyAPI install")
        return False


def check_ollama() -> bool:
    """Check if Ollama is reachable (vision + embedding)."""
    print("\n" + "=" * 60)
    print("7. Ollama (vision + embedding)")
    print("=" * 60)
    try:
        import httpx

        r = httpx.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            print(f"  ✓ Ollama reachable, {len(models)} models loaded")
            for m in models:
                print(f"    - {m}")

            needed = ["minicpm-v", "bge-m3"]
            for n in needed:
                if any(n in m for m in models):
                    print(f"  ✓ {n} available")
                else:
                    print(f"  ✗ {n} NOT found — run: ollama pull {n}")
            return True
        else:
            print(f"  ✗ Ollama returned {r.status_code}")
            return False
    except Exception as e:
        print(f"  ✗ Ollama not reachable: {e}")
        print("    Start it: ollama serve")
        return False


def check_qdrant() -> bool:
    """Check if Qdrant is running."""
    print("\n" + "=" * 60)
    print("8. Qdrant (vector DB)")
    print("=" * 60)
    try:
        import httpx

        r = httpx.get("http://localhost:6333/healthz", timeout=3)
        if r.status_code == 200:
            print("  ✓ Qdrant healthy at localhost:6333")
            return True
        else:
            print(f"  ✗ Qdrant returned {r.status_code}")
            return False
    except Exception as e:
        print(f"  ✗ Qdrant not reachable: {e}")
        print("    Start it: docker compose up -d qdrant")
        return False


def main() -> None:
    """Run all GPU and model checks."""
    print("\n🔍 EMILY GPU & MODEL PREFLIGHT CHECK")
    print("=" * 60)

    results: dict[str, bool] = {}
    results["nvidia"] = check_nvidia_smi()
    results["cuda"] = check_cuda_torch()
    results["stt"] = check_faster_whisper()
    results["tts"] = check_kokoro()
    results["vad"] = check_silero_vad()
    results["tabbyapi"] = check_tabbyapi()
    results["ollama"] = check_ollama()
    results["qdrant"] = check_qdrant()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    critical_ok = True
    for name, ok in results.items():
        icon = "✓" if ok else "✗"
        print(f"  {icon} {name}")
        if name in ("nvidia", "cuda", "tabbyapi") and not ok:
            critical_ok = False

    if critical_ok:
        print("\n✅ GPU and critical services ready!")
        print("   Run Emily: python main.py --no-gui")
    else:
        print("\n❌ Critical issues found — fix them before starting Emily:")
        if not results["nvidia"]:
            print("   • GPU not detected — check NVIDIA drivers")
        if not results["cuda"]:
            print("   • PyTorch CUDA not working — reinstall torch with CUDA")
        if not results["tabbyapi"]:
            print("   • TabbyAPI not running — LLM models need it for GPU inference")

    sys.exit(0 if critical_ok else 1)


if __name__ == "__main__":
    main()
