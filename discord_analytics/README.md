# Emily Discord Analytics Bot

🤖 A powerful Discord bot for real-time server monitoring, message analysis, and hacking-style analytics tools.

## Features

### 📊 Analytics Dashboard
- Real-time message tracking
- User activity monitoring
- Channel statistics
- Emoji usage analytics
- Voice activity tracking
- System resource monitoring

### 🛠️ Hacking Tools
- Message edit/delete logging
- User behavior analysis
- Export data to JSON
- Database storage for historical data
- System resource integration

### 📈 Commands
- `!emily-dashboard` - Show main analytics dashboard
- `!emily-user-stats [@user]` - Detailed user statistics
- `!emily-channel-stats [#channel]` - Channel analytics
- `!emily-export-data` - Export all analytics data

## Installation

1. **Clone and setup:**
   ```bash
   cd /home/supernovyl/Emily1.0/discord_analytics
   chmod +x setup.sh
   ./setup.sh
   ```

2. **Create Discord Bot:**
   - Go to https://discord.com/developers/applications
   - Create New Application → Bot
   - Copy the bot token
   - Enable Privileged Gateway Intents:
     - Server Members Intent
     - Message Content Intent

3. **Configure:**
   ```bash
   # Edit .env file
   nano .env
   # Add your bot token
   DISCORD_BOT_TOKEN=your_token_here
   ```

4. **Run:**
   ```bash
   python bot.py
   ```

## Database

The bot uses SQLite for data storage:
- `analytics.db` - Main database file
- Tables: `message_logs`, `user_activity`, `channel_stats`
- Automatic backups and exports

## Integration with Emily

This bot can be integrated with Emily's terminal interface:
- Real-time monitoring dashboard
- Command integration via Emily's command system
- System resource sharing
- Unified analytics interface

## Security Features

- Local database storage
- No external API calls
- Configurable data retention
- Privacy-focused design
- Bot token encryption support

## Performance

- Efficient database queries
- Background task processing
- Memory-optimized data structures
- Automatic cleanup routines

## Troubleshooting

**Bot won't start:**
- Check bot token in .env
- Verify Discord application permissions
- Ensure all dependencies installed

**No data showing:**
- Bot needs time to collect data
- Check bot has proper permissions
- Verify database file creation

**Memory issues:**
- Reduce update frequency in code
- Clear old database entries
- Monitor system resources

## Development

Extend the bot with:
- Custom analytics metrics
- Additional Discord events
- Integration with Emily modules
- Custom dashboard themes
- API endpoints for external access
