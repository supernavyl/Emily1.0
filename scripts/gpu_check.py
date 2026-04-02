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
                "    Install PyTorch with CUDA: uv add torch --index-url https://download.pytorch.org/whl/cu124"
            )
            return False
    except ImportError:
        print("  ✗ PyTorch not installed")
        return False


def check_moonshine_stt() -> bool:
    """Check Moonshine ONNX (STT)."""
    print("\n" + "=" * 60)
    print("3. Moonshine ONNX (STT) — CPU")
    print("=" * 60)
    try:
        import moonshine_onnx  # type: ignore[import-untyped]  # noqa: F401

        print("  ✓ moonshine-onnx installed")
        return True
    except ImportError:
        print("  ✗ moonshine-onnx not installed")
        print("    Install: uv add moonshine-onnx")
        return False


def check_tts() -> bool:
    """Check Orpheus TTS (primary) and Kokoro (fallback)."""
    print("\n" + "=" * 60)
    print("4. TTS — Orpheus (primary) + Kokoro (fallback)")
    print("=" * 60)
    ok = True
    try:
        import snac  # type: ignore[import-untyped]  # noqa: F401

        print("  ✓ snac installed (Orpheus neural codec)")
    except ImportError:
        print("  ✗ snac not installed (Orpheus TTS unavailable)")
        print("    Install: uv add snac")
        ok = False
    try:
        import llama_cpp  # type: ignore[import-untyped]  # noqa: F401

        print("  ✓ llama-cpp-python installed (Orpheus GGUF inference)")
    except ImportError:
        print("  ✗ llama-cpp-python not installed")
        ok = False
    try:
        import kokoro  # type: ignore[import-untyped]  # noqa: F401

        print("  ✓ kokoro installed (TTS fallback)")
    except ImportError:
        print("  ⚠ kokoro not installed (fallback TTS unavailable)")
    return ok


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


def check_llamacpp() -> bool:
    """Check llama-cpp-python (primary LLM backend)."""
    print("\n" + "=" * 60)
    print("6. llama-cpp-python (LLM backend)")
    print("=" * 60)
    try:
        import llama_cpp  # type: ignore[import-untyped]  # noqa: F401

        print("  ✓ llama-cpp-python installed")
        return True
    except ImportError:
        print("  ✗ llama-cpp-python not installed")
        print("    Install: uv add llama-cpp-python")
        return False


def check_ollama() -> bool:
    """Check if Ollama is reachable (vision + embedding)."""
    print("\n" + "=" * 60)
    print("7. Ollama (vision + embedding — optional)")
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
    results["stt"] = check_moonshine_stt()
    results["tts"] = check_tts()
    results["vad"] = check_silero_vad()
    results["llamacpp"] = check_llamacpp()
    results["ollama"] = check_ollama()
    results["qdrant"] = check_qdrant()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    critical_ok = True
    for name, ok in results.items():
        icon = "✓" if ok else "✗"
        print(f"  {icon} {name}")
        if name in ("nvidia", "cuda", "llamacpp") and not ok:
            critical_ok = False

    if critical_ok:
        print("\n✅ GPU and critical services ready!")
        print("   Run Emily: uv run python main.py --no-gui")
    else:
        print("\n❌ Critical issues found — fix them before starting Emily:")
        if not results["nvidia"]:
            print("   • GPU not detected — check NVIDIA drivers")
        if not results["cuda"]:
            print("   • PyTorch CUDA not working — reinstall torch with CUDA")
        if not results["llamacpp"]:
            print("   • llama-cpp-python not installed — needed for LLM inference")

    sys.exit(0 if critical_ok else 1)


if __name__ == "__main__":
    main()
