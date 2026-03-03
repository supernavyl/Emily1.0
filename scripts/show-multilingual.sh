#!/usr/bin/env bash
# Display Emily's multilingual capabilities

cat << 'EOF'

╔══════════════════════════════════════════════════════════════════════════╗
║                                                                          ║
║                    ✅ EMILY IS MULTILINGUAL! 🌍                          ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝

🤖 MODELS EMILY USES:

   TEXT GENERATION (119 languages):
   • Qwen3-4B    → Fast routing, classification
   • Qwen3-14B   → Standard conversation
   • QwQ-32B     → Complex reasoning, math

   VISION (multilingual):
   • MiniCPM-V 2.6 → Screen & camera understanding

   SPEECH (99 languages):
   • Faster-Whisper large-v3-turbo → Voice recognition

   TTS (English + 13 languages):
   • Kokoro → Fast English voice
   • XTTS v2 → 13 languages with voice cloning

🌍 LANGUAGE SUPPORT:

   ✅ 119 languages for TEXT (chat, documents, code)
   ✅ 99 languages for VOICE recognition (STT)
   ✅ MULTILINGUAL vision and document search
   ✅ AUTOMATIC language detection (no config needed!)

   Top languages: English, Chinese, Spanish, French, German,
                  Russian, Japanese, Korean, Arabic, Portuguese,
                  + 109 more!

💬 HOW TO USE:

   Just talk or type in YOUR language!
   Emily automatically detects and responds in the same language.

   Examples:
     Spanish:  "Hola Emily, ¿cómo estás?"
     French:   "Bonjour Emily, comment vas-tu?"
     Chinese:  "你好 Emily，你好吗？"
     Japanese: "こんにちは Emily、元気ですか？"

📚 FULL DOCUMENTATION:

   cat MODELS_AND_LANGUAGES.md
   cat MULTILINGUAL_QUICKREF.txt

   Or read online:
   - MODELS_AND_LANGUAGES.md (complete guide)
   - README.md (Operations Guide section)

🚀 START USING:

   ./scripts/start-emily.sh gui

   Then chat or speak in any of 119 languages!

╔══════════════════════════════════════════════════════════════════════════╗
║  Emily speaks your language natively — 100% local, no cloud! 🎉          ║
╚══════════════════════════════════════════════════════════════════════════╝

EOF
