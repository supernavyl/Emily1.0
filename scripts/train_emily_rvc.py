#!/usr/bin/env python3
"""
Train an RVC v2 model on Emily's Kokoro TTS voice.

Pipeline:
  1. Generate ~200 training sentences through Kokoro -> WAV files
  2. Preprocess (slice, normalize, denoise) via Applio
  3. Extract features (RMVPE f0 + HuBERT embeddings)
  4. Train RVC v2 (300 epochs, batch 8, RTX 4090)
  5. Copy model to data/rvc_models/emily.pth

Usage:
    uv run python scripts/train_emily_rvc.py

Time estimate on RTX 4090: ~25-35 minutes total.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path

# ── paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent.resolve()
APPLIO = ROOT / "tools" / "applio"
DATASET_DIR = ROOT / "data" / "rvc_dataset" / "emily_raw"
MODEL_OUT = ROOT / "data" / "rvc_models"
MODEL_NAME = "emily_rvc"
SAMPLE_RATE = 40000  # 40 kHz — best quality for RVC v2

# ── training sentences (phonetically diverse, natural speech rhythm) ──────────
TRAINING_SENTENCES = [
    # Conversational
    "Hey there, how's your day going so far?",
    "I've been thinking about that problem we discussed yesterday.",
    "That's a really interesting perspective, I hadn't considered it that way.",
    "Let me walk you through this step by step.",
    "Actually, I think there might be a simpler approach here.",
    "You know what, that actually makes a lot of sense.",
    "I'm curious what you think about that.",
    "Hmm, give me a moment to think about this.",
    "That's a great question, and I have a few thoughts on it.",
    "I completely understand why you'd feel that way.",
    # Technical
    "The neural network processes each token through multiple attention layers.",
    "When you initialize the gradient descent optimizer, set the learning rate carefully.",
    "The function returns a tensor of shape batch size by sequence length.",
    "We can parallelize this operation across all available GPU cores.",
    "Memory bandwidth is often the bottleneck in large language model inference.",
    "The transformer architecture uses self-attention to capture long-range dependencies.",
    "I recommend using a cosine learning rate schedule with warmup.",
    "The model achieves strong performance on several standard benchmarks.",
    "This regularization technique helps prevent overfitting on small datasets.",
    "Let me explain the difference between batch and layer normalization.",
    # Narrative
    "The morning light filtered through the tall windows of the library.",
    "She walked quickly down the empty hallway, footsteps echoing.",
    "After three years of research, the answer finally became clear.",
    "The city below was quiet, wrapped in an early fog.",
    "He had never seen anything quite like it before in his life.",
    "The experiment had been running for forty-eight hours without interruption.",
    "By the time they arrived, the storm had already passed.",
    "It was one of those rare moments when everything suddenly made sense.",
    "The old bookshop smelled of cedar and time.",
    "She typed quickly, fingers moving across the keyboard with practiced ease.",
    # Emotional range
    "I'm so excited to share this news with you!",
    "That's genuinely wonderful, congratulations on your achievement.",
    "I understand this is difficult, and I'm here to help.",
    "Don't worry, we'll figure this out together.",
    "This is absolutely fascinating, tell me more.",
    "I have to be honest, I'm a little concerned about this.",
    "Oh wow, I did not see that coming at all.",
    "That's hilarious, I can't believe that actually happened.",
    "I feel really proud of the work we've done here.",
    "We can definitely do better than this.",
    # Numbers and specifics
    "The temperature dropped to minus twelve degrees overnight.",
    "We processed over three million requests in the last twenty-four hours.",
    "The meeting is scheduled for two forty-five on Thursday afternoon.",
    "It takes approximately forty milliseconds for the first token to appear.",
    "The model has seven billion parameters and runs at sixteen bits.",
    "Our accuracy improved from eighty-three to ninety-one percent.",
    "Please download version three point two of the library.",
    "The cache stores up to one hundred and twenty-eight entries.",
    "I'll need about fifteen minutes to finish this analysis.",
    "The file is two point four gigabytes after compression.",
    # Phonetically rich
    "The quick brown fox jumps over the lazy sleeping dog.",
    "Whether the weather is warm or whether it's cold.",
    "She sells seashells by the seashore in the summer.",
    "The rhythm of the rain on the roof was relaxing.",
    "Vulnerability requires courage and emotional intelligence.",
    "Bureaucracy and philosophy often perplex people unnecessarily.",
    "The pharmaceutical company announced a revolutionary breakthrough.",
    "Simultaneously synchronizing several sophisticated systems.",
    "Exquisitely articulated, the speech captivated the entire audience.",
    "Supercalifragilistic is a word with many syllables.",
    # Questions
    "What's the most efficient way to handle this edge case?",
    "Have you considered using a hash map instead of a list?",
    "Could you explain why the gradient explodes in this scenario?",
    "Do you have a preference between these two approaches?",
    "Is there anything else I should know before we proceed?",
    "When would be the best time to run the full evaluation?",
    "Which architecture would you recommend for real-time inference?",
    "Can we schedule a quick call to discuss the implementation details?",
    "How long do you think the training process will take?",
    "What happens if the model encounters an unknown token?",
    # Long sentences
    "In the context of modern machine learning, the ability to generalize "
    "from limited training data remains one of the most challenging open problems.",
    "The integration of multiple sensory modalities enables richer and more "
    "nuanced understanding of complex real-world environments.",
    "When designing a conversational AI system, the trade-off between response "
    "quality and latency is one of the most critical engineering decisions.",
    "Recent advances in audio synthesis have made it possible to generate highly "
    "realistic speech with fine-grained control over prosody and emotion.",
    "The ability to reason about abstract concepts and apply them to concrete "
    "situations is what distinguishes intelligent systems from simple lookup tables.",
    # Short punchy
    "Got it.",
    "Absolutely.",
    "Let me check.",
    "One moment.",
    "Of course.",
    "Right away.",
    "Interesting.",
    "Makes sense.",
    "Good point.",
    "I agree.",
    "Tell me more.",
    "That works.",
    "Perfect.",
    "Not quite.",
    "Almost there.",
    "Let's try it.",
    "I'll handle it.",
    "Ready when you are.",
    "Here we go.",
    "Done.",
    # Stress and prosody variety
    "This changes everything.",
    "Are you absolutely sure about that decision?",
    "I really, truly, deeply appreciate your patience.",
    "Well, that's one way to look at it.",
    "The key insight, and this is crucial, is the attention mechanism.",
    "First, second, third: prioritize, delegate, eliminate.",
    "Not bad. Not great. But definitely a step forward.",
    "Yes and no, it depends entirely on the context.",
    "Let me be very clear: this is non-negotiable.",
    "Remarkable. Simply remarkable.",
]


def save_pcm_as_wav(pcm_bytes: bytes, path: Path, sample_rate: int = 24000) -> None:
    """Save raw int16 PCM bytes as a WAV file."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)


async def generate_dataset() -> None:
    """Generate training WAV files from Kokoro TTS."""
    print(f"\n{'=' * 60}")
    print("STEP 1: Generating Kokoro TTS training dataset")
    print(f"{'=' * 60}")
    print(f"Sentences : {len(TRAINING_SENTENCES)}")
    print(f"Output    : {DATASET_DIR}\n")

    DATASET_DIR.mkdir(parents=True, exist_ok=True)

    existing = list(DATASET_DIR.glob("*.wav"))
    if len(existing) >= len(TRAINING_SENTENCES):
        print(f"Dataset already complete ({len(existing)} files), skipping.")
        return

    sys.path.insert(0, str(ROOT))
    from config import get_settings
    from voice.tts import TTSManager

    settings = get_settings()
    tts = TTSManager(settings.tts)
    await tts.load()

    total_duration = 0.0
    for i, sentence in enumerate(TRAINING_SENTENCES):
        out_path = DATASET_DIR / f"emily_{i:04d}.wav"
        if out_path.exists():
            continue

        all_pcm = b""
        async for chunk in tts.speak(text=sentence):
            all_pcm += chunk

        if all_pcm:
            save_pcm_as_wav(all_pcm, out_path, sample_rate=24000)
            duration = len(all_pcm) / (24000 * 2)
            total_duration += duration
            print(f"  [{i + 1:3d}/{len(TRAINING_SENTENCES)}] {duration:.1f}s  {sentence[:55]!r}")

    print(f"\nDataset complete: {total_duration / 60:.1f} minutes of audio\n")


def run_step(name: str, script: Path, *args: str) -> None:
    """Run an Applio training script as a subprocess."""
    cmd = [sys.executable, str(script), *args]
    print(f"\n[{name}] Running ...")
    result = subprocess.run(cmd, cwd=str(APPLIO))
    if result.returncode != 0:
        raise RuntimeError(f"{name} failed (exit code {result.returncode})")
    print(f"[{name}] Done.")


def preprocess() -> None:
    print(f"\n{'=' * 60}")
    print("STEP 2: Preprocess — slice, normalize, denoise")
    print(f"{'=' * 60}")
    logs_dir = APPLIO / "logs" / MODEL_NAME
    run_step(
        "preprocess",
        APPLIO / "rvc" / "train" / "preprocess" / "preprocess.py",
        str(logs_dir),
        str(DATASET_DIR),
        str(SAMPLE_RATE),
        "8",  # cpu_cores
        "Simple",  # cut_preprocess ("Skip"/"Simple"/"Automatic")
        "False",  # process_effects
        "True",  # noise_reduction (removes TTS artifacts)
        "0.5",  # clean_strength
        "3.0",  # chunk_len seconds
        "0.3",  # overlap_len seconds
        "peak",  # normalization_mode
    )


def extract_features() -> None:
    print(f"\n{'=' * 60}")
    print("STEP 3: Extract — RMVPE f0 + HuBERT ContentVec features")
    print(f"{'=' * 60}")
    logs_dir = APPLIO / "logs" / MODEL_NAME
    run_step(
        "extract",
        APPLIO / "rvc" / "train" / "extract" / "extract.py",
        str(logs_dir),
        "rmvpe",  # f0 method — most accurate pitch detection
        "8",  # cpu_cores
        "0",  # gpu index
        str(SAMPLE_RATE),
        "contentvec",  # embedder — HuBERT ContentVec 768
        "None",  # embedder_model_custom
        "2",  # include_mutes
    )


def download_pretrained_base() -> None:
    """Download pretrained generator/discriminator weights for faster convergence."""
    pretrain_dir = APPLIO / "rvc" / "models" / "pretraineds" / "hifi-gan"
    g_path = pretrain_dir / "f0G40k.pth"
    d_path = pretrain_dir / "f0D40k.pth"
    if g_path.exists() and d_path.exists():
        print("\nPretrained base models already present, skipping download.")
        return
    print("\nDownloading pretrained base model weights ...")
    sys.path.insert(0, str(APPLIO))
    os.chdir(str(APPLIO))
    from rvc.lib.tools.prerequisites_download import prequisites_download_pipeline

    prequisites_download_pipeline(pretraineds_hifigan=True, models=True, exe=False)


def train() -> None:
    print(f"\n{'=' * 60}")
    print("STEP 4: Train RVC v2 — 300 epochs, batch 8, RTX 4090")
    print(f"{'=' * 60}")
    download_pretrained_base()

    # Pretrained model paths are relative to APPLIO dir (train.py uses os.getcwd())
    pretrain_dir = "rvc/models/pretraineds/hifi-gan"
    pretrain_g = f"{pretrain_dir}/f0G40k.pth"
    pretrain_d = f"{pretrain_dir}/f0D40k.pth"

    # train.py sys.argv order:
    # [1] model_name  [2] save_every_epoch  [3] total_epoch
    # [4] pretrainG   [5] pretrainD         [6] gpus
    # [7] batch_size  [8] sample_rate       [9] save_only_latest
    # [10] save_every_weights  [11] cache_data_in_gpu
    # [12] overtraining_detector  [13] overtraining_threshold
    # [14] cleanup    [15] vocoder           [16] checkpointing
    run_step(
        "train",
        APPLIO / "rvc" / "train" / "train.py",
        MODEL_NAME,  # [1] model name (determines logs/ subdir)
        "50",  # [2] save_every_epoch
        "300",  # [3] total_epoch
        pretrain_g,  # [4] pretrainG path (relative to APPLIO)
        pretrain_d,  # [5] pretrainD path (relative to APPLIO)
        "0",  # [6] gpu index
        "8",  # [7] batch_size
        str(SAMPLE_RATE),  # [8] sample_rate
        "True",  # [9] save_only_latest
        "False",  # [10] save_every_weights
        "False",  # [11] cache_data_in_gpu
        "False",  # [12] overtraining_detector
        "50",  # [13] overtraining_threshold
        "False",  # [14] cleanup
        "HiFi-GAN",  # [15] vocoder
        "False",  # [16] gradient checkpointing
    )


def build_index() -> None:
    """Build FAISS retrieval index for improved voice similarity."""
    print(f"\n{'=' * 60}")
    print("STEP 5: Build FAISS index for retrieval")
    print(f"{'=' * 60}")
    logs_dir = APPLIO / "logs" / MODEL_NAME
    index_script = APPLIO / "rvc" / "train" / "process" / "extract_index.py"
    if index_script.exists():
        run_step("index", index_script, str(logs_dir), "Auto")


def export_model() -> None:
    print(f"\n{'=' * 60}")
    print("STEP 6: Export model -> data/rvc_models/")
    print(f"{'=' * 60}")

    MODEL_OUT.mkdir(parents=True, exist_ok=True)
    logs_dir = APPLIO / "logs" / MODEL_NAME

    pth_files = sorted(logs_dir.glob("*.pth"), key=lambda p: p.stat().st_mtime)
    if not pth_files:
        raise FileNotFoundError(f"No .pth found in {logs_dir}")

    src_pth = pth_files[-1]
    dst_pth = MODEL_OUT / "emily.pth"
    shutil.copy2(src_pth, dst_pth)
    print(f"Copied: {src_pth.name} -> {dst_pth}")

    index_files = sorted(logs_dir.glob("*.index"), key=lambda p: p.stat().st_mtime)
    if index_files:
        dst_idx = MODEL_OUT / "emily.index"
        shutil.copy2(index_files[-1], dst_idx)
        print(f"Copied: {index_files[-1].name} -> {dst_idx}")

    print(f"\nModel ready: {dst_pth}")


async def main() -> None:
    print("\n" + "=" * 60)
    print("  Emily RVC Training Pipeline")
    print("  Voice source : Kokoro TTS (Emily's own voice)")
    print("  GPU          : RTX 4090  |  Epochs: 300")
    print("  F0 method    : RMVPE    |  SR: 40 kHz")
    print("=" * 60)

    await generate_dataset()
    preprocess()
    extract_features()
    train()
    build_index()
    export_model()

    print(f"\n{'=' * 60}")
    print("  Training complete! emily.pth is active.")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
