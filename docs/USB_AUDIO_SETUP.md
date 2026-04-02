# USB Headphone Setup for Emily

Emily should use your USB headphones instead of your built-in headset.

## Quick Setup

1. **Plug in your USB headphones** and make sure they're powered on

2. **Find your USB device IDs:**
   ```bash
   python find_usb_audio.py
   ```
   
   This will list all audio devices and highlight USB ones. You'll see output like:
   ```
   *** USB ***
   [Device 2] 
     Name: USB Audio Device
     Input channels: 1
     Output channels: 2
   ```

3. **Update `config.yaml`** with the device ID or name:
   ```yaml
   audio:
     input_device: 2          # Use device index
     output_device: 2
     # OR
     input_device: "USB Audio Device"   # Use device name
     output_device: "USB Audio Device"
   ```

4. **Start Emily:**
   ```bash
   python main.py
   ```

## Troubleshooting

**"No USB devices found"**
- Check the device is plugged in: `lsusb`
- Restart the USB device
- Check audio device manager: `pavucontrol`

**"Device not responding"**
- Try using the device index (number) instead of name
- Check for exclusive access from another app

**"Audio cutting out or echoing"**
- This is Acoustic Echo Cancellation (AEC). Emily is detecting the echo and filtering it.
- If too aggressive, adjust `perception/audio/aec.py` settings

**"Still using built-in audio"**
- Make sure both `input_device` AND `output_device` are set to USB
- Restart Emily after changing config
- Check if PulseAudio is overriding: `pacmd list-sources | grep -A 5 USB`

## Configuration Options

| Option | Type | Example | Notes |
|--------|------|---------|-------|
| `input_device` | int OR string | `2` or `"USB Audio"` | Microphone input |
| `output_device` | int OR string | `2` or `"USB Audio"` | Speaker/headphone output |

- **Use index** (0, 1, 2...) for most reliable device selection
- **Use name** for human-readable config
- Device name is case-insensitive and matches partial strings

## Advanced: Custom Audio Routing

If you need different devices for input vs. output:

```yaml
audio:
  input_device: 2           # USB microphone
  output_device: 3          # USB speakers
```

Or use device names:
```yaml
audio:
  input_device: "USB Microphone"
  output_device: "USB Headphones"
```
