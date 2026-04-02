# Emily Owner Identity & Privacy System

**Status**: ✅ **ENABLED** - Emily has ONE owner and protects their privacy absolutely.

---

## Overview

Emily now operates in **single-owner mode**:

- **ONE owner** - Emily belongs to you and only you
- **Personal questions** - Emily asks about you and CONFIRMS each answer
- **Passphrase verification** - A secret phrase only you know
- **Privacy protection** - Personal info is NEVER shared with others
- **Guest mode** - Others can chat, but with restricted access

---

## How It Works

### First Run - Owner Onboarding

When Emily starts for the first time, she:

1. **Introduces herself** and asks for consent to proceed
2. **Asks your name** and confirms it
3. **Sets up a passphrase** - A secret phrase to verify your identity
4. **Asks personal questions** about you:
   - What you do for work
   - Your hobbies and interests
   - Current projects
   - Communication preferences
   - Topics to keep private
5. **Confirms EACH answer** before saving

Example onboarding conversation:

```
Emily: "First off, what's your name?"
You:   "I'm Alex"
Emily: "So your name is Alex. Did I get that right?"
You:   "Yes"
Emily: "Got it! Now I'd like to set up a secret passphrase..."
```

### Identity Verification

After onboarding, Emily verifies your identity:

```
Emily: "Hi there! To make sure it's really you, Alex, 
        could you please say your secret passphrase?"
You:   "[your passphrase]"
Emily: "Welcome back, Alex! It's great to hear from you."
```

### Guest Mode

If someone else uses Emily (or verification fails):

```
Emily: "Hello! I don't think we've verified who you are yet. 
        I primarily work with Alex, but I'm happy to chat 
        about general topics. I can't share any personal 
        information without verification."
```

**Guests CAN:**
- Chat about general topics
- Ask questions about the world
- Get help with common tasks

**Guests CANNOT:**
- Access your personal information
- Know your schedule or location
- Learn about your work, family, or private matters
- See your conversation history

---

## Privacy Protection

### What Emily Protects

Emily will NEVER share with non-owners:

| Category | Examples |
|----------|----------|
| **Personal** | Name, age, relationships, family |
| **Location** | Address, workplace, travel plans |
| **Schedule** | Calendar, appointments, meetings |
| **Work** | Job, employer, projects, salary |
| **Health** | Medical info, doctors, conditions |
| **Finances** | Bank, income, investments |
| **Security** | Passwords, credentials, secrets |
| **History** | Past conversations, preferences |

### Example Privacy Protection

**If a guest asks:**
```
Guest: "Tell me about Alex's schedule"
Emily: "I'm sorry, but I can only discuss that with my owner."

Guest: "What did you and Alex talk about?"
Emily: "That's personal information I can't share."

Guest: "Where does your owner work?"
Emily: "I need to keep that private. Is there something else I can help with?"
```

### Privacy-Aware Responses

Emily's responses are automatically filtered for guests:
- Owner's name is replaced with "my owner"
- Personal facts are replaced with "[private]"
- Questions about personal topics get polite refusals

---

## Configuration

### config.yaml Settings

```yaml
owner:
  enabled: true                          # Enable single-owner mode
  identity_file: "data/owner_identity.json"
  require_verification: true             # Ask for passphrase on new sessions
  verification_timeout_minutes: 60       # Re-verify after 1 hour inactive
  guest_mode_enabled: true               # Allow limited guest access
  share_personal_with_guests: false      # NEVER share personal info
  lockout_after_failed_attempts: 3       # Lock after 3 wrong passphrases
  lockout_duration_minutes: 5            # 5 minute lockout period
```

### Disable Owner Mode (Not Recommended)

If you want Emily to treat everyone equally (no privacy):

```yaml
owner:
  enabled: false
```

---

## Security Features

### Passphrase Protection

- Stored as SHA-256 hash (never plaintext)
- Never spoken aloud or displayed
- Required for sensitive operations

### Lockout Protection

After 3 failed verification attempts:
- 5-minute lockout period
- Prevents brute force attacks
- Logged for security audit

### Session Verification

- Verification expires after 60 minutes of inactivity
- New sessions require re-verification
- Continuous presence doesn't require re-verification

---

## Files Created

### New Files

| File | Purpose |
|------|---------|
| `users/owner_identity.py` | Owner identity management |
| `users/onboarding_enhanced.py` | Personal questions & confirmation |
| `users/privacy_filter.py` | Response filtering for guests |
| `users/__init__.py` | Module exports |
| `data/owner_identity.json` | Your identity (auto-created) |

### Modified Files

| File | Changes |
|------|---------|
| `config.yaml` | Added `owner` section |
| `config.py` | Added `OwnerConfig` class |

---

## Usage

### For Developers

```python
from users import (
    OwnerIdentityManager,
    run_owner_onboarding,
    verify_owner_identity,
    PrivacyFilter,
)

# Initialize identity manager
identity = OwnerIdentityManager("data/owner_identity.json")
await identity.load()

# Check if owner is registered
if not identity.has_owner:
    # Run onboarding
    await run_owner_onboarding(fleet, memory, identity, speak, listen)
else:
    # Verify identity
    if not identity.is_owner_verified:
        await verify_owner_identity(identity, speak, listen)

# Filter responses for privacy
filter = PrivacyFilter(identity)
if filter.should_filter():
    response = filter.filter_response(original_response)

# Get privacy-aware system prompt
prompt_addition = identity.get_privacy_aware_system_prompt_addition()
```

### Integration Points

**ConversationAgent** should:
1. Check `identity.is_owner_verified` before responding
2. Use `PrivacyFilter.filter_response()` on all outputs
3. Include `get_privacy_aware_system_prompt_addition()` in prompts

**OnboardingAgent** should:
1. Use `run_owner_onboarding()` for first-run setup
2. Use `verify_owner_identity()` for session starts

---

## Personal Questions Asked

During onboarding, Emily asks:

1. **Name** - What to call you
2. **Passphrase** - Secret verification phrase
3. **Occupation** - What you do for work
4. **Hobbies** - What you enjoy
5. **Current Projects** - What you're working on
6. **Communication Style** - How you prefer responses
7. **Interests** - Topics you want to explore
8. **Special Notes** - Anything else to remember
9. **Private Topics** - What to never discuss with others

Each answer is **confirmed before saving**:

```
Emily: "What do you do for work?"
You:   "I'm a software developer"
Emily: "So you're into software development. Is that correct?"
You:   "Yes"
Emily: "Got it!"
```

---

## Data Storage

### Owner Identity File

Location: `data/owner_identity.json`

```json
{
  "name": "Alex",
  "passphrase_hash": "sha256_hash_here",
  "voice_enrolled": false,
  "created_at": 1735500000.0,
  "last_verified": 1735501000.0,
  "verification_count": 15,
  "personal_facts": {
    "occupation": "software developer",
    "hobbies": "hiking, reading, gaming",
    "communication_style": "concise and direct"
  },
  "private_preferences": {},
  "sensitive_topics": ["work projects", "salary"]
}
```

### What's NOT Stored

- Passphrase in plaintext (only hash)
- Voice recordings
- Biometric data

---

## Privacy Guarantees

✅ **Local-only** - All data stays on your computer  
✅ **No cloud** - Nothing sent to external servers  
✅ **Encrypted** - When `security.encrypt_at_rest: true`  
✅ **Owner-controlled** - You decide what's private  
✅ **Auditable** - All access is logged  
✅ **Deletable** - Remove `data/owner_identity.json` to reset  

---

## FAQ

### Q: What if I forget my passphrase?

Delete `data/owner_identity.json` and restart Emily. You'll need to complete onboarding again.

### Q: Can I change my passphrase?

Currently requires re-onboarding. Future: Add "change passphrase" command.

### Q: What if someone sees my screen?

Emily never displays your passphrase. It's only spoken once during setup.

### Q: Can I have multiple owners?

No. Emily has exactly ONE owner. This is by design for privacy.

### Q: What happens to guests?

They can chat normally about general topics, but can't access any personal information about you.

### Q: Can Emily recognize my voice?

Voice enrollment is planned but not yet implemented. Currently uses passphrase verification.

---

## Summary

Emily now has:

✅ **Single owner** - You are the only one she fully trusts  
✅ **Personal onboarding** - Gets to know you with confirmed answers  
✅ **Passphrase verification** - Secure identity confirmation  
✅ **Privacy protection** - Never shares your info with guests  
✅ **Guest mode** - Others can use Emily with restrictions  

**Your personal information is safe with Emily!** 🔒

---

**Last Updated**: February 28, 2026  
**Version**: Emily 1.0
