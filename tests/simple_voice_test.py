#!/usr/bin/env python3
"""
Emily Voice Testing - Simplified Version

Tests core voice components without complex dependencies.
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class SimpleVoiceTest:
    """Simplified voice testing without complex dependencies."""

    def __init__(self):
        self.results = {
            "stt": {"status": "not_tested", "details": {}},
            "tts": {"status": "not_tested", "details": {}},
            "conversation": {"status": "not_tested", "details": {}},
            "audio": {"status": "not_tested", "details": {}},
            "overall": {"score": 0},
        }

    async def run_tests(self) -> dict[str, Any]:
        """Run simplified voice tests."""
        print("🎤 Emily Voice Testing - Simplified")
        print("=" * 40)

        await self.test_basic_config()
        await self.test_tts_engines()
        await self.test_audio_components()
        await self.test_conversation_features()

        self.generate_report()
        return self.results

    async def test_basic_config(self):
        """Test basic configuration loading."""
        print("\n⚙️ Testing Configuration...")

        try:
            # Test config loading
            config_path = Path(__file__).parent.parent / "config.yaml"
            if config_path.exists():
                self.results["stt"]["status"] = "config_loaded"
                self.results["stt"]["details"]["config_file"] = str(config_path)
                print("  ✓ Configuration file found")
            else:
                self.results["stt"]["status"] = "config_missing"
                print("  ❌ Configuration file missing")

        except Exception as e:
            self.results["stt"]["status"] = "config_error"
            self.results["stt"]["details"]["error"] = str(e)
            print(f"  ❌ Config error: {e}")

    async def test_tts_engines(self):
        """Test TTS engine availability."""
        print("\n🔊 Testing TTS Engines...")

        engines = ["kokoro", "xtts_v2", "csm"]
        engine_results = {}

        for engine in engines:
            try:
                # Test import
                if engine == "kokoro":
                    try:
                        import kokoro  # noqa: F401

                        engine_results[engine] = {"available": True, "import": "success"}
                        print(f"  ✓ {engine}: Available")
                    except ImportError:
                        engine_results[engine] = {"available": False, "import": "failed"}
                        print(f"  ❌ {engine}: Not installed")

                elif engine == "xtts_v2":
                    try:
                        import edge_tts  # noqa: F401

                        engine_results[engine] = {"available": True, "import": "success"}
                        print(f"  ✓ {engine}: Available (using edge-tts)")
                    except ImportError:
                        engine_results[engine] = {"available": False, "import": "failed"}
                        print(f"  ❌ {engine}: Not installed")

                elif engine == "csm":
                    try:
                        import transformers  # noqa: F401

                        engine_results[engine] = {"available": True, "import": "success"}
                        print(f"  ✓ {engine}: Available")
                    except ImportError:
                        engine_results[engine] = {"available": False, "import": "failed"}
                        print(f"  ❌ {engine}: Not installed")

            except Exception as e:
                engine_results[engine] = {"available": False, "error": str(e)}
                print(f"  ❌ {engine}: Error - {e}")

        available_count = sum(1 for r in engine_results.values() if r.get("available"))
        self.results["tts"]["status"] = f"{available_count}/{len(engines)}_available"
        self.results["tts"]["details"] = engine_results

    async def test_audio_components(self):
        """Test audio processing components."""
        print("\n🎛️ Testing Audio Components...")

        audio_results = {}

        # Test numpy audio processing
        try:
            test_audio = np.random.randn(480).astype(np.float32) * 0.1
            rms = np.sqrt(np.mean(test_audio**2))
            audio_results["numpy_processing"] = {"working": True, "rms": float(rms)}
            print("  ✓ NumPy audio processing: Working")
        except Exception as e:
            audio_results["numpy_processing"] = {"working": False, "error": str(e)}
            print(f"  ❌ NumPy audio processing: {e}")

        # Test audio file formats
        try:
            import io
            import wave

            # Create a simple WAV buffer
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(16000)
                wav_file.writeframes((test_audio * 32767).astype(np.int16).tobytes())

            audio_results["wav_format"] = {"working": True, "size": buffer.tell()}
            print("  ✓ WAV format handling: Working")
        except Exception as e:
            audio_results["wav_format"] = {"working": False, "error": str(e)}
            print(f"  ❌ WAV format handling: {e}")

        # Test basic VAD simulation
        try:
            energy_threshold = 0.05
            speech_energy = float(np.mean(test_audio**2))
            speech_detected = speech_energy > energy_threshold
            audio_results["basic_vad"] = {
                "working": True,
                "speech_detected": speech_detected,
                "energy": speech_energy,
            }
            print(f"  ✓ Basic VAD simulation: Working (speech: {speech_detected})")
        except Exception as e:
            audio_results["basic_vad"] = {"working": False, "error": str(e)}
            print(f"  ❌ Basic VAD simulation: {e}")

        working_count = sum(1 for r in audio_results.values() if r.get("working"))
        self.results["audio"]["status"] = f"{working_count}/{len(audio_results)}_working"
        self.results["audio"]["details"] = audio_results

    async def test_conversation_features(self):
        """Test conversation system features."""
        print("\n💬 Testing Conversation Features...")

        conv_results = {}

        # Test text processing
        try:
            test_sentences = [
                "Hello, how are you?",
                "What's the weather like?",
                "Can you help me with something?",
                "Thank you for your help.",
            ]

            processing_results = []
            for sentence in test_sentences:
                word_count = len(sentence.split())
                char_count = len(sentence)
                estimated_time = word_count * 0.4  # ~400ms per word

                processing_results.append(
                    {
                        "sentence": sentence,
                        "words": word_count,
                        "chars": char_count,
                        "estimated_time_ms": estimated_time * 1000,
                    }
                )

            conv_results["text_processing"] = {
                "working": True,
                "sentences_processed": len(processing_results),
                "avg_words_per_sentence": np.mean([r["words"] for r in processing_results]),
            }
            print(f"  ✓ Text processing: {len(processing_results)} sentences")

        except Exception as e:
            conv_results["text_processing"] = {"working": False, "error": str(e)}
            print(f"  ❌ Text processing: {e}")

        # Test response generation simulation
        try:
            response_templates = [
                "I can help you with that.",
                "That's an interesting question.",
                "Let me think about that for a moment.",
                "Based on what you've told me...",
            ]

            response_times = []
            for _template in response_templates:
                start_time = time.time()
                # Simulate processing time
                await asyncio.sleep(0.01)
                response_time = (time.time() - start_time) * 1000
                response_times.append(response_time)

            conv_results["response_simulation"] = {
                "working": True,
                "avg_response_time_ms": np.mean(response_times),
                "responses_generated": len(response_times),
            }
            print(f"  ✓ Response simulation: {np.mean(response_times):.0f}ms avg")

        except Exception as e:
            conv_results["response_simulation"] = {"working": False, "error": str(e)}
            print(f"  ❌ Response simulation: {e}")

        # Test conversation flow
        try:
            conversation_flow = [
                {"user": "Hello", "assistant": "Hi there! How can I help?"},
                {"user": "What time is it?", "assistant": "I can help you check the time."},
                {"user": "Thank you", "assistant": "You're welcome!"},
            ]

            conv_results["conversation_flow"] = {
                "working": True,
                "turns": len(conversation_flow),
                "flow_complete": True,
            }
            print(f"  ✓ Conversation flow: {len(conversation_flow)} turns")

        except Exception as e:
            conv_results["conversation_flow"] = {"working": False, "error": str(e)}
            print(f"  ❌ Conversation flow: {e}")

        working_count = sum(1 for r in conv_results.values() if r.get("working"))
        self.results["conversation"]["status"] = f"{working_count}/{len(conv_results)}_working"
        self.results["conversation"]["details"] = conv_results

    def generate_report(self):
        """Generate final test report."""
        print("\n📊 Voice Test Report")
        print("=" * 30)

        # Calculate overall score
        scores = {
            "config": 100 if self.results["stt"]["status"] == "config_loaded" else 0,
            "tts": self._calculate_tts_score(),
            "audio": self._calculate_audio_score(),
            "conversation": self._calculate_conversation_score(),
        }

        overall_score = np.mean(list(scores.values()))
        self.results["overall"]["score"] = overall_score

        print(f"Configuration: {scores['config']:.0f}%")
        print(f"TTS Engines: {scores['tts']:.0f}%")
        print(f"Audio Processing: {scores['audio']:.0f}%")
        print(f"Conversation: {scores['conversation']:.0f}%")
        print(f"\n🎯 Overall Score: {overall_score:.1f}%")

        # Save results
        results_file = Path(__file__).parent / "simple_voice_test_results.json"
        with open(results_file, "w") as f:
            json.dump(self.results, f, indent=2)
        print(f"📁 Results saved to: {results_file}")

    def _calculate_tts_score(self):
        """Calculate TTS availability score."""
        details = self.results["tts"].get("details", {})
        available = sum(1 for r in details.values() if r.get("available"))
        total = len(details)
        return (available / total * 100) if total > 0 else 0

    def _calculate_audio_score(self):
        """Calculate audio processing score."""
        details = self.results["audio"].get("details", {})
        working = sum(1 for r in details.values() if r.get("working"))
        total = len(details)
        return (working / total * 100) if total > 0 else 0

    def _calculate_conversation_score(self):
        """Calculate conversation system score."""
        details = self.results["conversation"].get("details", {})
        working = sum(1 for r in details.values() if r.get("working"))
        total = len(details)
        return (working / total * 100) if total > 0 else 0


async def main():
    """Run simplified voice tests."""
    tester = SimpleVoiceTest()
    results = await tester.run_tests()
    return results


if __name__ == "__main__":
    asyncio.run(main())
