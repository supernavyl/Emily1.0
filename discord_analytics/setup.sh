#!/bin/bash
# Discord Analytics Bot Setup Script

echo "🤖 Setting up Emily Discord Analytics Bot..."

# Check if we're in a conda environment
if command -v conda &> /dev/null && [ -n "$CONDA_DEFAULT_ENV" ]; then
    echo "📦 Using conda environment: $CONDA_DEFAULT_ENV"
    INSTALL_CMD="conda install -c conda-forge"
else
    echo "📦 Using pip"
    INSTALL_CMD="pip install"
fi

# Install dependencies
echo "📥 Installing dependencies..."
$INSTALL_CMD discord.py psutil matplotlib seaborn pandas

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "🔧 Creating .env file..."
    cat > .env << EOF
DISCORD_BOT_TOKEN=YOUR_BOT_TOKEN_HERE
DISCORD_BOT_PREFIX=!emily-
EOF
    echo "⚠️  Please edit .env and add your Discord bot token"
fi

# Make bot executable
chmod +x bot.py

echo "✅ Setup complete!"
echo "📝 Next steps:"
echo "   1. Get a bot token from https://discord.com/developers/applications"
echo "   2. Edit .env and add your token"
echo "   3. Run: python bot.py"
