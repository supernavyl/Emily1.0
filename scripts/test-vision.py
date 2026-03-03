#!/usr/bin/env python3
"""
Quick test script to verify Emily's vision system is working.

Tests:
1. Camera access (OpenCV)
2. Screen capture (mss)
3. Vision config loading
4. Optional: DeepFace emotion detection
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


async def test_camera():
    """Test webcam capture."""
    print("📹 Testing camera access...")
    try:
        import cv2

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("   ❌ Could not open camera device 0")
            return False

        ret, frame = cap.read()
        cap.release()

        if ret and frame is not None:
            print(f"   ✅ Camera working! Frame shape: {frame.shape}")
            return True
        else:
            print("   ❌ Camera opened but could not read frame")
            return False

    except ImportError:
        print("   ❌ opencv-python not installed")
        print("      Install with: pip install opencv-python")
        return False
    except Exception as e:
        print(f"   ❌ Camera test failed: {e}")
        return False


async def test_screen_capture():
    """Test screen capture."""
    print("\n🖥️  Testing screen capture...")
    try:
        import mss

        with mss.mss() as sct:
            monitor = sct.monitors[1]  # Primary monitor
            screenshot = sct.grab(monitor)
            print(
                f"   ✅ Screen capture working! Resolution: {screenshot.width}x{screenshot.height}"
            )
            return True

    except ImportError:
        print("   ❌ mss not installed")
        print("      Install with: pip install mss")
        return False
    except Exception as e:
        print(f"   ❌ Screen capture test failed: {e}")
        return False


async def test_config():
    """Test vision config loading."""
    print("\n⚙️  Testing vision configuration...")
    try:
        from config import load_config

        config = load_config()

        if not config.vision.enabled:
            print("   ⚠️  Vision is DISABLED in config.yaml")
            print("      Enable with: vision.enabled = true")
            return False

        print("   ✅ Vision enabled in config")
        print(f"      - Screen capture interval: {config.vision.screen_capture_interval_s}s")
        print(f"      - Webcam device: {config.vision.webcam_device}")
        print(f"      - Emotion detection: {config.vision.emotion_detection}")
        return True

    except Exception as e:
        print(f"   ❌ Config test failed: {e}")
        return False


async def test_emily_vision_pipeline():
    """Test Emily's vision pipeline integration."""
    print("\n🔍 Testing Emily vision pipeline...")
    try:
        from config import load_config
        from perception.vision.screen_capture import ScreenCapture
        from perception.vision.webcam import WebcamCapture

        config = load_config()

        # Test screen capture
        screen = ScreenCapture(config.vision)
        await screen.init()

        if screen._available:
            screenshot = await screen.capture_once()
            if screenshot:
                print("   ✅ Screen capture initialized and working")
            else:
                print("   ⚠️  Screen capture initialized but capture returned None")
        else:
            print("   ⚠️  Screen capture not available")

        # Test webcam
        webcam = WebcamCapture(config.vision)
        await webcam.init()

        if webcam.is_available:
            frame_b64, meta = await webcam.capture_frame()
            if frame_b64:
                print("   ✅ Webcam capture initialized and working")
                if "emotions" in meta:
                    print(f"      - Detected emotions: {meta['emotions']}")
            else:
                print("   ⚠️  Webcam initialized but capture returned None")
        else:
            print("   ⚠️  Webcam not available")

        webcam.release()
        return True

    except ImportError as e:
        print(f"   ❌ Missing dependency: {e}")
        return False
    except Exception as e:
        print(f"   ❌ Pipeline test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_emotion_detection():
    """Test optional DeepFace emotion detection."""
    print("\n😊 Testing emotion detection (optional)...")
    try:
        from deepface import DeepFace  # noqa: F401

        print("   ✅ DeepFace is installed and available")
        return True
    except ImportError:
        print("   ℹ️  DeepFace not installed (optional)")
        print("      Install with: pip install deepface tf-keras")
        return None  # Not an error, just optional


async def main():
    """Run all vision tests."""
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Emily Vision System Tests")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    results = {}

    # Run tests
    results["camera"] = await test_camera()
    results["screen"] = await test_screen_capture()
    results["config"] = await test_config()
    results["emotion"] = await test_emotion_detection()
    results["pipeline"] = await test_emily_vision_pipeline()

    # Summary
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Test Summary")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    for test_name, result in results.items():
        if result is True:
            status = "✅ PASS"
        elif result is None:
            status = "ℹ️  OPTIONAL"
        else:
            status = "❌ FAIL"
        print(f"{status:15} {test_name}")

    # Overall result
    print()
    critical_tests = ["camera", "screen", "config", "pipeline"]
    all_critical_pass = all(results.get(t, False) for t in critical_tests)

    if all_critical_pass:
        print("🎉 All critical tests passed! Vision system is ready.")
        print("\nNext steps:")
        print("  1. Start Emily: ./scripts/start-emily.sh gui")
        print("  2. Ask Emily: 'What's on my screen?'")
        print("  3. Test webcam: 'Can you see me?'")
        return 0
    else:
        print("⚠️  Some tests failed. Review the output above.")
        print("\nTroubleshooting:")
        print("  • Run: ./scripts/setup-vision.sh")
        print("  • Check: docs/VISION_SETUP.md")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
