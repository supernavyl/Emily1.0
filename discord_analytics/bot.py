#!/usr/bin/env python3
"""
Emily Discord Analytics Bot
Real-time server monitoring, message analysis, and hacking-style tools
"""

import json
import os
import sqlite3
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import discord
import psutil
from discord.ext import commands, tasks

# Configuration
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
DB_PATH = Path(__file__).parent / "analytics.db"


class DiscordAnalyticsBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        intents.presences = True

        super().__init__(
            command_prefix="!emily-",
            intents=intents,
            help_command=None,
            activity=discord.Activity(
                type=discord.ActivityType.watching, name="🤖 Analyzing server data..."
            ),
        )

        self.analytics_data = defaultdict(
            lambda: {
                "messages": 0,
                "reactions": 0,
                "mentions": 0,
                "attachments": 0,
                "edits": 0,
                "deletes": 0,
                "voice_time": 0,
                "last_active": None,
            }
        )

        self.server_stats = {
            "total_messages": 0,
            "active_channels": set(),
            "active_users": set(),
            "emoji_usage": Counter(),
            "command_usage": Counter(),
            "voice_activity": defaultdict(int),
            "member_joins": 0,
            "member_leaves": 0,
            "start_time": datetime.now(),
        }

        self.init_database()

    def init_database(self):
        """Initialize SQLite database for analytics storage."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS message_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER UNIQUE,
                author_id INTEGER,
                channel_id INTEGER,
                guild_id INTEGER,
                content TEXT,
                timestamp DATETIME,
                edit_count INTEGER DEFAULT 0,
                deleted BOOLEAN DEFAULT FALSE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_activity (
                user_id INTEGER,
                guild_id INTEGER,
                messages_sent INTEGER DEFAULT 0,
                voice_minutes INTEGER DEFAULT 0,
                reactions_given INTEGER DEFAULT 0,
                last_active DATETIME,
                PRIMARY KEY (user_id, guild_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS channel_stats (
                channel_id INTEGER,
                guild_id INTEGER,
                message_count INTEGER DEFAULT 0,
                unique_users INTEGER DEFAULT 0,
                peak_activity_hour INTEGER,
                last_message DATETIME,
                PRIMARY KEY (channel_id, guild_id)
            )
        """)

        conn.commit()
        conn.close()

    async def on_ready(self):
        print(f"🤖 {self.user} has connected to Discord!")
        print(f"📊 Analytics database: {DB_PATH}")
        print(f"🔍 Monitoring {len(self.guilds)} servers")

        # Start background tasks
        self.analytics_update.start()
        self.system_monitor.start()

    async def on_message(self, message):
        """Log and analyze every message."""
        if message.author.bot:
            return

        # Update stats
        self.server_stats["total_messages"] += 1
        self.server_stats["active_channels"].add(message.channel.id)
        self.server_stats["active_users"].add(message.author.id)

        # User analytics
        user_data = self.analytics_data[message.author.id]
        user_data["messages"] += 1
        user_data["last_active"] = datetime.now()

        # Count mentions
        user_data["mentions"] += len(message.mentions)

        # Count attachments
        user_data["attachments"] += len(message.attachments)

        # Count emojis
        for emoji in message.content:
            if emoji in ["😀", "😂", "❤️", "🔥", "👍", "😎", "🤔", "😭", "😡", "👀"]:
                self.server_stats["emoji_usage"][emoji] += 1

        # Store in database
        await self.log_message(message)

        # Process commands
        await self.process_commands(message)

    async def on_message_edit(self, before, after):
        """Track message edits."""
        if after.author.bot:
            return

        self.analytics_data[after.author.id]["edits"] += 1

        # Update database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE message_logs
            SET edit_count = edit_count + 1, content = ?
            WHERE message_id = ?
        """,
            (after.content, after.id),
        )
        conn.commit()
        conn.close()

    async def on_message_delete(self, message):
        """Track message deletions."""
        if message.author.bot:
            return

        self.analytics_data[message.author.id]["deletes"] += 1

        # Update database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE message_logs
            SET deleted = TRUE
            WHERE message_id = ?
        """,
            (message.id,),
        )
        conn.commit()
        conn.close()

    async def on_raw_reaction_add(self, payload):
        """Track reaction additions."""
        if payload.member and payload.member.bot:
            return

        self.analytics_data[payload.user_id]["reactions"] += 1

    async def on_member_join(self, member):
        """Track new members."""
        self.server_stats["member_joins"] += 1

    async def on_member_remove(self, member):
        """Track member leaves."""
        self.server_stats["member_leaves"] += 1

    async def on_voice_state_update(self, member, before, after):
        """Track voice activity."""
        if member.bot:
            return

        if after.channel and not before.channel:
            # Joined voice
            self.server_stats["voice_activity"][member.id] = time.time()
        elif (
            not after.channel
            and before.channel
            and member.id in self.server_stats["voice_activity"]
        ):
            duration = time.time() - self.server_stats["voice_activity"][member.id]
            self.analytics_data[member.id]["voice_time"] += duration
            del self.server_stats["voice_activity"][member.id]

    async def log_message(self, message):
        """Store message in database."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT OR REPLACE INTO message_logs
                (message_id, author_id, channel_id, guild_id, content, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    message.id,
                    message.author.id,
                    message.channel.id,
                    message.guild.id,
                    message.content[:1000],  # Limit content length
                    message.created_at,
                ),
            )
            conn.commit()
        except Exception as e:
            print(f"Database error: {e}")
        finally:
            conn.close()

    @tasks.loop(minutes=5)
    async def analytics_update(self):
        """Update analytics dashboard."""
        # Update user activity table
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        for user_id, data in self.analytics_data.items():
            cursor.execute(
                """
                INSERT OR REPLACE INTO user_activity
                (user_id, guild_id, messages_sent, voice_minutes, reactions_given, last_active)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    user_id,
                    1,  # Default guild ID for now
                    data["messages"],
                    int(data["voice_time"] / 60),
                    data["reactions"],
                    data["last_active"],
                ),
            )

        conn.commit()
        conn.close()

    @tasks.loop(minutes=1)
    async def system_monitor(self):
        """Monitor system resources."""
        cpu_percent = psutil.cpu_percent()
        memory = psutil.virtual_memory()

        # Update bot status with system info
        activity = discord.Activity(
            type=discord.ActivityType.watching, name=f"CPU: {cpu_percent}% | RAM: {memory.percent}%"
        )
        await self.change_presence(activity=activity)

    # Commands
    @commands.command(name="dashboard")
    async def dashboard(self, ctx):
        """Show analytics dashboard."""
        embed = discord.Embed(
            title="🤖 Emily Analytics Dashboard",
            color=discord.Color.green(),
            timestamp=datetime.now(),
        )

        # Server stats
        uptime = datetime.now() - self.server_stats["start_time"]
        embed.add_field(
            name="📊 Server Statistics",
            value=f"""
**Total Messages:** {self.server_stats["total_messages"]:,}
**Active Channels:** {len(self.server_stats["active_channels"])}
**Active Users:** {len(self.server_stats["active_users"])}
**Uptime:** {uptime.days}d {uptime.seconds // 3600}h
**Members Joined:** {self.server_stats["member_joins"]}
**Members Left:** {self.server_stats["member_leaves"]}
            """.strip(),
            inline=False,
        )

        # Top emojis
        top_emojis = self.server_stats["emoji_usage"].most_common(5)
        emoji_text = "\n".join([f"{emoji}: {count}" for emoji, count in top_emojis])
        embed.add_field(name="😀 Top Emojis", value=emoji_text or "No emoji data yet", inline=False)

        # System stats
        cpu = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        embed.add_field(
            name="💻 System Resources",
            value=f"""
**CPU Usage:** {cpu}%
**Memory Usage:** {memory.percent}%
**Available RAM:** {memory.available / (1024**3):.1f} GB
            """.strip(),
            inline=False,
        )

        embed.set_footer(text="Emily Analytics Bot | Real-time monitoring")
        await ctx.send(embed=embed)

    @commands.command(name="user-stats")
    async def user_stats(self, ctx, member: discord.Member = None):
        """Show detailed statistics for a user."""
        member = member or ctx.author
        data = self.analytics_data[member.id]

        embed = discord.Embed(
            title=f"👤 User Analytics: {member.display_name}",
            color=member.color,
            timestamp=datetime.now(),
        )

        embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(
            name="📈 Activity Metrics",
            value=f"""
**Messages:** {data["messages"]:,}
**Mentions:** {data["mentions"]:,}
**Attachments:** {data["attachments"]:,}
**Reactions:** {data["reactions"]:,}
**Edits:** {data["edits"]:,}
**Deletes:** {data["deletes"]:,}
**Voice Time:** {int(data["voice_time"] / 60)}m
            """.strip(),
            inline=False,
        )

        if data["last_active"]:
            embed.add_field(
                name="⏰ Last Active",
                value=data["last_active"].strftime("%Y-%m-%d %H:%M:%S"),
                inline=False,
            )

        await ctx.send(embed=embed)

    @commands.command(name="channel-stats")
    async def channel_stats(self, ctx, channel: discord.TextChannel = None):
        """Show statistics for a channel."""
        channel = channel or ctx.channel

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT COUNT(*) as message_count, COUNT(DISTINCT author_id) as unique_users
            FROM message_logs
            WHERE channel_id = ?
        """,
            (channel.id,),
        )

        result = cursor.fetchone()
        conn.close()

        embed = discord.Embed(
            title=f"📊 Channel Analytics: #{channel.name}",
            color=discord.Color.blue(),
            timestamp=datetime.now(),
        )

        if result:
            embed.add_field(
                name="📈 Statistics",
                value=f"""
**Total Messages:** {result[0]:,}
**Unique Users:** {result[1]:,}
**Messages per User:** {result[0] / max(result[1], 1):.1f}
**Created:** {channel.created_at.strftime("%Y-%m-%d")}
                """.strip(),
                inline=False,
            )

        await ctx.send(embed=embed)

    @commands.command(name="export-data")
    async def export_data(self, ctx):
        """Export analytics data to JSON."""
        data = {
            "server_stats": dict(self.server_stats),
            "user_analytics": dict(self.analytics_data),
            "export_time": datetime.now().isoformat(),
            "total_users": len(self.analytics_data),
        }

        # Convert datetime objects to strings
        for _user_id, user_data in data["user_analytics"].items():
            if user_data["last_active"]:
                user_data["last_active"] = user_data["last_active"].isoformat()

        file_content = json.dumps(data, indent=2)

        # Create file
        file_path = Path(__file__).parent / f"analytics_export_{int(time.time())}.json"
        with open(file_path, "w") as f:
            f.write(file_content)

        await ctx.send(
            f"📁 Analytics data exported to `{file_path.name}`", file=discord.File(file_path)
        )


def main():
    bot = DiscordAnalyticsBot()
    bot.run(BOT_TOKEN)


if __name__ == "__main__":
    main()
