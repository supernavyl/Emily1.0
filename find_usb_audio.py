#!/usr/bin/env python3
"""
USB Audio Device Finder — Detect available USB headphones.

Run this to find the correct device names for your USB headphones,
then update config.yaml with input_device and output_device.
"""

import sys

try:
    import sounddevice as sd
except ImportError:
    print("ERROR: sounddevice not installed")
    print("Install with: uv add sounddevice")
    sys.exit(1)


def find_usb_devices() -> None:
    """List all available audio devices and highlight USB ones."""
    devices = sd.query_devices()

    print("=" * 80)
    print("ALL AUDIO DEVICES")
    print("=" * 80)

    usb_inputs = []
    usb_outputs = []

    for i, device in enumerate(devices):
        name = device.get("name", "Unknown")
        max_input_channels = device.get("max_input_channels", 0)
        max_output_channels = device.get("max_output_channels", 0)

        is_usb = "usb" in name.lower()
        marker = "*** USB ***" if is_usb else ""

        print(f"\n[Device {i}] {marker}")
        print(f"  Name: {name}")
        print(f"  Input channels: {max_input_channels}")
        print(f"  Output channels: {max_output_channels}")
        print(f"  Sample rate: {device.get('default_samplerate', 'N/A')} Hz")

        if is_usb:
            if max_input_channels > 0:
                usb_inputs.append((i, name))
            if max_output_channels > 0:
                usb_outputs.append((i, name))

    print("\n" + "=" * 80)
    print("USB DEVICES DETECTED")
    print("=" * 80)

    if usb_inputs:
        print("\nUSB INPUT DEVICES (microphones):")
        for idx, name in usb_inputs:
            print(f"  - Device {idx}: {name}")
            print(f'    Use in config.yaml: input_device: {idx}  # or: "{name}"')
    else:
        print("\nNo USB input devices found!")

    if usb_outputs:
        print("\nUSB OUTPUT DEVICES (speakers/headphones):")
        for idx, name in usb_outputs:
            print(f"  - Device {idx}: {name}")
            print(f'    Use in config.yaml: output_device: {idx}  # or: "{name}"')
    else:
        print("\nNo USB output devices found!")

    if not usb_inputs and not usb_outputs:
        print("\n⚠️  No USB audio devices detected!")
        print("Check that your USB headphones are:")
        print("  1. Plugged in")
        print("  2. Powered on")
        print("  3. Recognized by the OS (try: lsusb)")
    else:
        print("\n✓ Found USB devices. Update config.yaml with the indices above.")

    # Also show default device
    print("\n" + "=" * 80)
    print("DEFAULT DEVICE")
    print("=" * 80)
    default_in = sd.default.device[0]
    default_out = sd.default.device[1]
    print(f"Input:  Device {default_in} ({devices[default_in]['name']})")
    print(f"Output: Device {default_out} ({devices[default_out]['name']})")


if __name__ == "__main__":
    find_usb_devices()
