# Emily Terminal Interface

A rich Textual-based terminal interface for Emily with comprehensive command system and application launchers.

## Features

### 🎯 Core Functionality
- **Live Chat Interface** - Real-time conversation with Emily
- **System Status Panel** - CPU, RAM, VRAM monitoring with FSM state
- **Memory View** - Working memory and episodic session data
- **Log Viewer** - System logs with filtering
- **Command System** - Comprehensive terminal commands

### 🚀 Command System

#### Help Commands
- `/help` - Show main help menu
- `/help apps` - List all available applications
- `/help commands` - List all commands
- `/help <command>` - Help for specific command

#### Application Launchers
- `/start brain` - Launch Brain Dashboard (PySide6)
- `/start voice` - Launch Voice Dashboard (PySide6)
- `/start chat` - Launch Desktop Chat App (PySide6)
- `/start terminal` - Launch Terminal UI (Textual)
- `/start api` - Start FastAPI server
- `/start web` - Launch Web Dashboard (React)
- `/start core` - Start Emily Core (voice OS)
- `/start all` - Start complete Emily stack

#### System Control
- `/stop <app>` - Stop an application
- `/restart <app>` - Restart an application
- `/status` - Show running applications
- `/health` - Check system health
- `/metrics` - Show system metrics
- `/logs <app>` - Show application logs
- `/clear` - Clear terminal screen

#### Command Aliases
- `h, ?` - help
- `run, launch` - start
- `kill, terminate` - stop
- `reload, reboot` - restart
- `ps, list` - status
- `check` - health
- `stats` - metrics
- `cls, clean` - clear

## Usage

### Running the Terminal

```bash
# From Emily root directory
python -m ui.terminal.app

# Or directly
python ui/terminal/app.py
```

### Command Examples

```bash
# Get help
/help

# List applications
/help apps

# Start Brain Dashboard
/start brain

# Check what's running
/status

# View system metrics
/metrics

# Start complete stack
/start all

# Stop API server
/stop api

# Clear screen
/clear
```

## Available Applications

### Brain Dashboard
- **Purpose**: Real-time cognitive state monitoring
- **Features**: Agent activity, memory operations, system metrics
- **Technology**: PySide6

### Voice Dashboard
- **Purpose**: Audio pipeline controls and conversation state
- **Features**: TTS/STT status, emotion detection, speaker identification
- **Technology**: PySide6

### Desktop Chat App
- **Purpose**: Chat interface with conversation history
- **Features**: Profiles, Emily persona customization
- **Technology**: PySide6

### Terminal UI
- **Purpose**: Terminal-based interface
- **Features**: Chat, memory view, system logs, command access
- **Technology**: Textual

### API Server
- **Purpose**: REST API and WebSocket server
- **Features**: Web interfaces, external integrations
- **Technology**: FastAPI

### Web Dashboard
- **Purpose**: Browser-based interface
- **Features**: Full Emily functionality
- **Technology**: React

### Emily Core
- **Purpose**: Main voice OS engine
- **Features**: Conversation engine, perception, memory, agents
- **Technology**: Python

## Architecture

### Command System
- **Command Registry**: Central command registration and dispatch
- **Application Manager**: Process lifecycle management
- **Help System**: Structured help content with search
- **Result Handling**: Standardized command results

### File Structure
```
ui/terminal/
├── app.py              # Main terminal application
├── commands.py         # Command implementations
├── help_system.py      # Help content and formatting
└── README.md           # This documentation
```

## Dependencies

### Required
- Python 3.8+
- Textual (for TUI)

### Optional
- psutil (for system metrics)
- structlog (for logging)

## Installation

```bash
# Install textual for the TUI
pip install textual

# Install psutil for system metrics
pip install psutil

# Install structlog for logging
pip install structlog
```

## Development

### Adding New Commands

1. Create command function in `commands.py`
2. Register with `@registry.register()`
3. Add help content to `help_system.py`
4. Update documentation

Example:
```python
@registry.register("mycommand", aliases=["mc"])
async def cmd_mycommand(args: list[str]) -> CommandResult:
    """My custom command."""
    return CommandResult(True, "Command executed successfully")
```

### Testing

Run the demo script to test functionality without dependencies:
```bash
python terminal_demo.py
```

## Integration

The terminal integrates with Emily's core systems:
- **Agent Bus**: For communication with Emily agents
- **Bootstrap**: For application lifecycle
- **Observability**: For logging and metrics
- **Configuration**: For settings and preferences

## Theme

The terminal uses a purple/black cyberpunk theme:
- Background: Pure black (#000000)
- Text: Bright magenta (#ff00ff)
- Accents: Various purple shades
- Compatible with Windsurf editor theme

## Troubleshooting

### Common Issues

1. **ModuleNotFoundError: No module named 'textual'**
   ```bash
   pip install textual
   ```

2. **ModuleNotFoundError: No module named 'psutil'**
   ```bash
   pip install psutil
   ```

3. **Applications won't start**
   - Check dependencies are installed
   - Verify Emily configuration
   - Check system logs with `/logs <app>`

### Debug Mode

Enable debug logging by setting environment variable:
```bash
export EMILY_LOG_LEVEL=DEBUG
python -m ui.terminal.app
```
