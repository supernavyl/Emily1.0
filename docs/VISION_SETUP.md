# Emily Vision System Setup

This guide walks you through enabling camera and screen access for Emily's vision capabilities.

## Features

Once enabled, Emily can:
- 📹 **Webcam capture**: Access your camera for presence detection
- 🖥️ **Screen capture**: Capture screenshots for visual context
- 😊 **Emotion detection** (optional): Analyze facial expressions with DeepFace
- 👁️ **Vision understanding**: Use MiniCPM-V to understand visual content

## Quick Setup

### 1. Enable Vision in Config

Vision is now **enabled** in `config.yaml`:

```yaml
vision:
  enabled: true
  screen_capture_interval_s: 5
  webcam_device: 0
  emotion_detection: true  # Set to false if you don't want facial analysis
```

### 2. Run Setup Script

```bash
chmod +x scripts/setup-vision.sh
./scripts/setup-vision.sh
```

This script will:
- ✅ Check and install required Python packages (opencv-python, mss, Pillow)
- ✅ Verify camera permissions
- ✅ Test camera access
- ✅ Test screen capture
- ✅ Add you to the `video` group if needed

### 3. Install Optional Emotion Detection

If you want facial expression analysis (emotion_detection: true), install DeepFace:

```bash
# Activate the virtual environment
source .venv/bin/activate

# Install DeepFace (this will download TensorFlow models on first use)
pip install deepface tf-keras

# Note: DeepFace requires TensorFlow, which is a large dependency (~500MB)
# If you don't need emotion detection, set emotion_detection: false in config.yaml
```

## Linux Permissions

### Camera Access

On Linux, you need to be in the `video` group to access camera devices:

```bash
# Check if you're in the video group
groups

# Add yourself to video group (the setup script does this)
sudo usermod -a -G video $USER

# Log out and back in for changes to take effect
```

### Screen Capture

Emily's screen capture works best on **X11**. If you're running Wayland:

```bash
# Check your session type
echo $XDG_SESSION_TYPE

# If Wayland, screen capture may have limitations
# Consider switching to X11 or using XWayland for full functionality
```

## Configuration Options

In `config.yaml`:

```yaml
vision:
  enabled: true                          # Master enable/disable
  screen_capture_interval_s: 5           # Seconds between screenshots
  webcam_device: 0                       # Camera device index (0 = default)
  emotion_detection: true                # Enable facial expression analysis
```

## Testing

### Test Camera

```python
import cv2

cap = cv2.VideoCapture(0)
if cap.isOpened():
    ret, frame = cap.read()
    if ret:
        print(f"✅ Camera working! Frame shape: {frame.shape}")
    cap.release()
else:
    print("❌ Could not open camera")
```

### Test Screen Capture

```python
import mss

with mss.mss() as sct:
    monitor = sct.monitors[1]
    screenshot = sct.grab(monitor)
    print(f"✅ Screen capture working! {screenshot.width}x{screenshot.height}")
```

## Troubleshooting

### Camera Not Found

**Problem**: `/dev/video*` devices don't exist

**Solutions**:
1. Check if camera is physically connected
2. Check if camera is enabled in BIOS
3. Verify kernel drivers: `lsmod | grep video`
4. Try `v4l2-ctl --list-devices` to see available devices

### Permission Denied

**Problem**: `Permission denied` when accessing camera

**Solutions**:
1. Ensure you're in the `video` group: `groups`
2. Log out and back in after being added to the group
3. Check device permissions: `ls -la /dev/video0`

### Screen Capture Not Working on Wayland

**Problem**: Screen capture returns black or fails on Wayland

**Solutions**:
1. Switch to X11 session (recommended for Emily)
2. Use XWayland compatibility layer
3. Grant screen recording permission in system settings

### DeepFace Installation Issues

**Problem**: TensorFlow/DeepFace installation fails

**Solutions**:
1. Use Python 3.11 (TensorFlow wheels may not be available for 3.12+)
2. Install without DeepFace and disable emotion detection
3. Consider CPU-only TensorFlow if GPU version fails

## Architecture

Emily's vision pipeline:

```
┌─────────────────────────────────────────────────────────┐
│  Vision Pipeline (perception/vision/)                   │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Screen Capture (mss)                                   │
│    ├─ Every 5s (configurable)                           │
│    ├─ Resizes to max 1024px width                       │
│    └─ Base64-encoded PNG                                │
│                                                          │
│  Webcam Capture (OpenCV)                                │
│    ├─ Every 5s (configurable)                           │
│    ├─ Optional DeepFace emotion analysis (every 15s)    │
│    └─ Base64-encoded JPEG                               │
│                                                          │
│  Vision LLM (MiniCPM-V via Ollama)                      │
│    ├─ Analyzes screenshots and webcam frames            │
│    ├─ Answers questions about visual content            │
│    └─ Provides context for conversation                 │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## Privacy & Security

Emily's vision system:
- ✅ **100% local**: All processing happens on your machine
- ✅ **No cloud**: Images never leave your system
- ✅ **Encrypted storage**: Vision data encrypted at rest (if security.encrypt_at_rest: true)
- ✅ **On-demand**: Vision only active when Emily is running
- ✅ **Configurable**: Full control over what's captured and when

## Performance

Typical VRAM usage with vision enabled:

| Component | VRAM |
|-----------|------|
| MiniCPM-V 2.6 | ~8 GB |
| Fast model (Qwen3-14B) | ~10 GB |
| Nano model (Qwen3-4B) | ~3 GB |
| **Total** | **~21 GB** |

With RTX 4090 (24 GB), you have headroom for vision + text models.

## Next Steps

Once vision is enabled:

1. **Start Emily**: `./scripts/start-emily.sh gui`
2. **Test vision**: Ask Emily "What's on my screen?" or "Can you see me?"
3. **Monitor**: Check logs for `screen_capture_initialized` and `webcam_initialized`

## References

- OpenCV: https://opencv.org/
- mss (Multi-Screen Shot): https://python-mss.readthedocs.io/
- DeepFace: https://github.com/serengil/deepface
- MiniCPM-V: https://github.com/OpenBMB/MiniCPM-V
