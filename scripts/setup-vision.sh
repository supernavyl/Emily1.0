#!/usr/bin/env bash
#
# Setup script for Emily vision system (camera + screen access)
# Run this to enable webcam and screen capture capabilities.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Emily Vision System Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if running on Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo "⚠️  This script is designed for Linux systems."
    echo "   For other OS, manual setup may be required."
fi

# 1. Check for required dependencies
echo "📦 Checking Python dependencies..."
cd "$PROJECT_ROOT"

if [[ ! -d ".venv" ]]; then
    echo "❌ Virtual environment not found. Run 'uv sync --extra gpu-cuda' first."
    exit 1
fi

source .venv/bin/activate

# Check opencv-python
if ! python -c "import cv2" 2>/dev/null; then
    echo "⚠️  opencv-python not installed. Installing..."
    uv pip install opencv-python
else
    echo "✅ opencv-python is installed"
fi

# Check mss
if ! python -c "import mss" 2>/dev/null; then
    echo "⚠️  mss not installed. Installing..."
    uv pip install mss
else
    echo "✅ mss is installed"
fi

# Check Pillow
if ! python -c "import PIL" 2>/dev/null; then
    echo "⚠️  Pillow not installed. Installing..."
    uv pip install Pillow
else
    echo "✅ Pillow is installed"
fi

echo ""

# 2. Check camera access
echo "📹 Checking camera access..."

# Check if user is in video group
if ! groups | grep -q video; then
    echo "⚠️  User is not in 'video' group. Adding..."
    echo "   This requires sudo and a re-login to take effect."
    sudo usermod -a -G video "$USER"
    echo "✅ Added to 'video' group. Please log out and back in for changes to take effect."
    NEEDS_RELOGIN=1
else
    echo "✅ User is in 'video' group"
fi

# List available video devices
if ls /dev/video* &>/dev/null; then
    echo "✅ Found video devices:"
    ls -la /dev/video* | awk '{print "   " $0}'
else
    echo "⚠️  No /dev/video* devices found. Check if camera is connected."
fi

echo ""

# 3. Check screen capture capabilities
echo "🖥️  Checking screen capture capabilities..."

# Check display server
if [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
    echo "⚠️  Running on Wayland. Screen capture may have limitations."
    echo "   Emily uses mss which works best on X11."
    echo "   For full screen capture, consider switching to X11 or using xwayland."
elif [[ -n "${DISPLAY:-}" ]]; then
    echo "✅ Running on X11 - screen capture fully supported"
else
    echo "⚠️  No display server detected. Running headless?"
fi

echo ""

# 4. Test camera access
echo "🧪 Testing camera access..."

cat > /tmp/test_camera.py << 'EOF'
import sys
try:
    import cv2
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Could not open camera device 0")
        sys.exit(1)
    ret, frame = cap.read()
    cap.release()
    if ret and frame is not None:
        print(f"✅ Camera test successful! Frame shape: {frame.shape}")
    else:
        print("❌ Camera opened but could not read frame")
        sys.exit(1)
except Exception as e:
    print(f"❌ Camera test failed: {e}")
    sys.exit(1)
EOF

if python /tmp/test_camera.py; then
    CAMERA_OK=1
else
    CAMERA_OK=0
fi
rm /tmp/test_camera.py

echo ""

# 5. Test screen capture
echo "🧪 Testing screen capture..."

cat > /tmp/test_screen.py << 'EOF'
import sys
import os
try:
    import mss
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # Primary monitor
        screenshot = sct.grab(monitor)
        print(f"✅ Screen capture test successful! Resolution: {screenshot.width}x{screenshot.height}")
except Exception as e:
    print(f"❌ Screen capture test failed: {e}")
    sys.exit(1)
EOF

if python /tmp/test_screen.py; then
    SCREEN_OK=1
else
    SCREEN_OK=0
fi
rm /tmp/test_screen.py

echo ""

# 6. Check config.yaml
echo "⚙️  Checking Emily configuration..."

if grep -q "enabled: true" "$PROJECT_ROOT/config.yaml" | grep -A2 "^vision:" | grep -q "enabled: true"; then
    echo "✅ Vision is enabled in config.yaml"
else
    echo "⚠️  Vision is disabled in config.yaml"
    echo "   Update config.yaml to enable: vision.enabled = true"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Setup Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [[ ${CAMERA_OK:-0} -eq 1 ]]; then
    echo "✅ Camera access: WORKING"
else
    echo "❌ Camera access: NOT WORKING"
fi

if [[ ${SCREEN_OK:-0} -eq 1 ]]; then
    echo "✅ Screen capture: WORKING"
else
    echo "❌ Screen capture: NOT WORKING"
fi

echo ""

if [[ ${NEEDS_RELOGIN:-0} -eq 1 ]]; then
    echo "⚠️  ACTION REQUIRED: Log out and back in for group changes to take effect."
    echo ""
fi

if [[ ${CAMERA_OK:-0} -eq 1 && ${SCREEN_OK:-0} -eq 1 ]]; then
    echo "🎉 Vision system is ready!"
    echo ""
    echo "Next steps:"
    echo "  1. Ensure vision.enabled = true in config.yaml (already done)"
    echo "  2. Start Emily: ./scripts/start-emily.sh gui"
    echo "  3. Emily will now have webcam and screen capture capabilities"
else
    echo "⚠️  Some vision components need attention (see above)."
fi

echo ""
