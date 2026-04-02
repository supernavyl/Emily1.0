#!/usr/bin/env python3
"""
Emily Audio Device Test — verify mic (Yeti Nano) and speakers (USB headphones).

Tests:
  1. List all audio devices and find yours
  2. Record 3 seconds from Yeti Nano
  3. Play it back through USB headphones
"""

from __future__ import annotations

import sys

import numpy as np


def find_device(name_fragment: str, kind: str) -> int | None:
    """Find a device index by partial name match.

    Skips generic/hardware devices (index 0, 'default', 'sysdefault')
    and prefers named devices with real channel counts.

    Args:
        name_fragment: Substring to match in device name.
        kind: 'input' or 'output'.

    Returns:
        Device index or None.
    """
    import sounddevice as sd  # type: ignore[import-untyped]

    devices = sd.query_devices()
    skip = {"default", "sysdefault", "portaudio"}
    for i, dev in enumerate(devices):
        ch_key = "max_input_channels" if kind == "input" else "max_output_channels"
        name_lower = dev["name"].lower()
        if any(s in name_lower for s in skip):
            continue
        if dev[ch_key] > 0 and name_fragment.lower() in name_lower:
            return i
    return None


def list_devices() -> None:
    """Print all audio devices."""
    import sounddevice as sd  # type: ignore[import-untyped]

    devices = sd.query_devices()
    print("=" * 70)
    print("ALL AUDIO DEVICES")
    print("=" * 70)
    for i, dev in enumerate(devices):
        inp = dev["max_input_channels"]
        out = dev["max_output_channels"]
        sr = int(dev["default_samplerate"])
        tag = ""
        if "yeti" in dev["name"].lower():
            tag = " ◄── YETI NANO"
        elif "usb" in dev["name"].lower():
            tag = " ◄── USB HEADPHONES"
        print(f"  [{i:2d}] {dev['name']:<45} in={inp} out={out} {sr}Hz{tag}")


def test_mic(device_idx: int, duration: float = 3.0, sr: int = 48000) -> np.ndarray:
    """Record audio from mic.

    Args:
        device_idx: Sounddevice input device index.
        duration: Seconds to record.
        sr: Sample rate.

    Returns:
        Recorded float32 audio array.
    """
    import sounddevice as sd  # type: ignore[import-untyped]

    print(f"\n🎤 Recording {duration}s from device {device_idx}...")
    print("   Speak now!")
    audio = sd.rec(
        int(duration * sr),
        samplerate=sr,
        channels=1,
        dtype="float32",
        device=device_idx,
    )
    sd.wait()

    rms = float(np.sqrt(np.mean(audio**2)))
    peak = float(np.max(np.abs(audio)))
    print(f"   Done. RMS={rms:.4f}  Peak={peak:.4f}")

    if rms < 0.001:
        print("   ⚠️  Very quiet — mic may not be picking up audio")
    else:
        print("   ✓ Audio captured successfully")

    return audio.flatten()


def test_speaker(device_idx: int, audio: np.ndarray, sr: int = 48000) -> None:
    """Play audio through speaker.

    Args:
        device_idx: Sounddevice output device index.
        audio: Float32 audio to play.
        sr: Sample rate.
    """
    import sounddevice as sd  # type: ignore[import-untyped]

    print(f"\n🔊 Playing back through device {device_idx}...")
    sd.play(audio, samplerate=sr, device=device_idx)
    sd.wait()
    print("   ✓ Playback complete")


def test_tone(device_idx: int, sr: int = 48000) -> None:
    """Play a test tone through speakers.

    Args:
        device_idx: Sounddevice output device index.
        sr: Sample rate.
    """
    import sounddevice as sd  # type: ignore[import-untyped]

    print(f"\n🔔 Playing test tone through device {device_idx}...")
    duration = 1.0
    t = np.linspace(0, duration, int(sr * duration), dtype=np.float32)
    # 440Hz sine wave at moderate volume
    tone = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    sd.play(tone, samplerate=sr, device=device_idx)
    sd.wait()
    print("   ✓ Tone complete — did you hear it?")


def main() -> None:
    """Run the full mic + speaker test."""
    try:
        import sounddevice as sd  # type: ignore[import-untyped]  # noqa: F401
    except ImportError:
        print("✗ sounddevice not installed")
        print("  Install: uv add sounddevice")
        sys.exit(1)

    print("\n🔍 EMILY AUDIO DEVICE TEST")

    # Step 1: List all devices
    list_devices()

    # Step 2: Find Yeti Nano (input)
    mic_idx = find_device("Yeti Nano", "input")
    if mic_idx is None:
        # Try broader USB search
        mic_idx = find_device("Yeti", "input")
    if mic_idx is None:
        print("\n✗ Yeti Nano not found!")
        print("  Check it's plugged in: lsusb | grep -i yeti")
        print("  Or check PulseAudio: pactl list sources short")
        mic_ok = False
    else:
        print(f"\n✓ Yeti Nano found at device index {mic_idx}")
        mic_ok = True

    # Step 3: Find USB headphones (output)
    spk_idx = find_device("USB Audio Speakers", "output")
    if spk_idx is None:
        spk_idx = find_device("USB Audio Front Headphones", "output")
    if spk_idx is None:
        spk_idx = find_device("USB", "output")
    if spk_idx is None:
        print("\n✗ USB headphones not found!")
        print("  Check they're plugged in: lsusb")
        print("  Or check PulseAudio: pactl list sinks short")
        spk_ok = False
    else:
        print(f"✓ USB output found at device index {spk_idx}")
        spk_ok = True

    # Step 4: Test tone on speakers
    if spk_ok:
        test_tone(spk_idx)

    # Step 5: Record from mic
    if mic_ok:
        audio = test_mic(mic_idx)

        # Step 6: Play back through USB headphones
        if spk_ok and float(np.max(np.abs(audio))) > 0.001:
            test_speaker(spk_idx, audio)

    # Summary
    print("\n" + "=" * 70)
    print("RESULT")
    print("=" * 70)
    if mic_ok:
        print(f"  ✓ Mic:     Yeti Nano (device {mic_idx})")
        print(f"             config.yaml: input_device: {mic_idx}")
    else:
        print("  ✗ Mic:     NOT FOUND")

    if spk_ok:
        print(f"  ✓ Speaker: USB headphones (device {spk_idx})")
        print(f"             config.yaml: output_device: {spk_idx}")
    else:
        print("  ✗ Speaker: NOT FOUND")

    if mic_ok and spk_ok:
        print("\n✅ Audio devices working! Update config.yaml if indices differ:")
        print(f"   input_device: {mic_idx}")
        print(f"   output_device: {spk_idx}")
    else:
        print("\n❌ Fix missing devices above, then re-run this test.")

    sys.exit(0 if (mic_ok and spk_ok) else 1)


if __name__ == "__main__":
    main()
