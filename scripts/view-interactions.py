#!/usr/bin/env python3
"""
Export and view Emily's saved interactions.

This script provides various utilities for accessing Emily's complete
interaction history, which is saved to data/interactions.db.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import load_config
from memory.interaction_logger import InteractionLogger


async def export_all(logger: InteractionLogger, output_path: str) -> None:
    """Export all interactions to JSON."""
    print(f"Exporting all interactions to {output_path}...")
    count = await logger.export_to_json(output_path)
    print(f"✅ Exported {count} interactions")


async def export_session(logger: InteractionLogger, session_id: str, output_path: str) -> None:
    """Export a specific session to JSON."""
    print(f"Exporting session {session_id} to {output_path}...")
    count = await logger.export_to_json(output_path, session_id=session_id)
    print(f"✅ Exported {count} interactions from session {session_id}")


async def view_recent(logger: InteractionLogger, n: int = 20, role: str | None = None) -> None:
    """View recent interactions."""
    interactions = await logger.get_recent_interactions(n=n, role=role)

    if not interactions:
        print("No interactions found")
        return

    print(f"\n📜 Showing {len(interactions)} most recent interactions:")
    print("=" * 80)

    for interaction in reversed(interactions):  # Show oldest first
        role_emoji = "👤" if interaction.role == "user" else "🤖"
        role_label = "USER" if interaction.role == "user" else "EMILY"

        print(f"\n{role_emoji} {role_label} [{interaction.created_at:.0f}]")
        print(f"   Session: {interaction.session_id[:8]}")
        print(
            f"   Content: {interaction.content[:200]}{'...' if len(interaction.content) > 200 else ''}"
        )
        if interaction.metadata:
            print(f"   Metadata: {json.dumps(interaction.metadata, indent=2)}")


async def search(logger: InteractionLogger, query: str, limit: int = 20) -> None:
    """Search interactions by content."""
    print(f"🔍 Searching for: '{query}'")
    interactions = await logger.search_interactions(query, limit=limit)

    if not interactions:
        print("No matches found")
        return

    print(f"\n📜 Found {len(interactions)} matching interactions:")
    print("=" * 80)

    for interaction in interactions:
        role_emoji = "👤" if interaction.role == "user" else "🤖"
        role_label = "USER" if interaction.role == "user" else "EMILY"

        print(f"\n{role_emoji} {role_label} [{interaction.created_at:.0f}]")
        print(f"   Session: {interaction.session_id[:8]}")
        print(
            f"   Content: {interaction.content[:200]}{'...' if len(interaction.content) > 200 else ''}"
        )


async def view_session(logger: InteractionLogger, session_id: str) -> None:
    """View all interactions from a specific session."""
    print(f"📜 Loading session {session_id}...")
    interactions = await logger.get_session_interactions(session_id)

    if not interactions:
        print(f"No interactions found for session {session_id}")
        return

    print(f"\n📜 Session {session_id} ({len(interactions)} interactions):")
    print("=" * 80)

    for interaction in interactions:
        role_emoji = "👤" if interaction.role == "user" else "🤖"
        role_label = "USER" if interaction.role == "user" else "EMILY"

        print(f"\n{role_emoji} {role_label}")
        print(f"   {interaction.content}")


async def stats(logger: InteractionLogger) -> None:
    """Show interaction statistics."""
    total = await logger.count_interactions()
    user_count = await logger.count_interactions(role="user")
    assistant_count = await logger.count_interactions(role="assistant")

    print("\n📊 Interaction Statistics:")
    print("=" * 80)
    print(f"Total interactions:     {total:,}")
    print(f"User messages:          {user_count:,}")
    print(f"Emily responses:        {assistant_count:,}")
    print(f"Average exchange ratio: {assistant_count / user_count if user_count > 0 else 0:.2f}")


async def backup(logger: InteractionLogger) -> None:
    """Create a manual backup."""
    print("Creating backup...")
    backup_path = await logger.create_backup()
    print(f"✅ Backup created: {backup_path}")


async def main():
    parser = argparse.ArgumentParser(
        description="Export and view Emily's saved interactions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # View recent interactions
  python scripts/view-interactions.py recent --n 50

  # View only user messages
  python scripts/view-interactions.py recent --role user --n 20

  # Search for interactions
  python scripts/view-interactions.py search "python code"

  # Export all to JSON
  python scripts/view-interactions.py export-all output.json

  # View statistics
  python scripts/view-interactions.py stats

  # Create manual backup
  python scripts/view-interactions.py backup
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Recent command
    recent_parser = subparsers.add_parser("recent", help="View recent interactions")
    recent_parser.add_argument("--n", type=int, default=20, help="Number of interactions to show")
    recent_parser.add_argument("--role", choices=["user", "assistant"], help="Filter by role")

    # Search command
    search_parser = subparsers.add_parser("search", help="Search interactions")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--limit", type=int, default=20, help="Max results")

    # Session command
    session_parser = subparsers.add_parser("session", help="View specific session")
    session_parser.add_argument("session_id", help="Session ID")

    # Export all command
    export_all_parser = subparsers.add_parser("export-all", help="Export all interactions to JSON")
    export_all_parser.add_argument("output", help="Output JSON file path")

    # Export session command
    export_session_parser = subparsers.add_parser("export-session", help="Export session to JSON")
    export_session_parser.add_argument("session_id", help="Session ID")
    export_session_parser.add_argument("output", help="Output JSON file path")

    # Stats command
    subparsers.add_parser("stats", help="Show interaction statistics")

    # Backup command
    subparsers.add_parser("backup", help="Create manual backup")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Load config and initialize logger
    config = load_config()
    logger = InteractionLogger(
        db_path=config.memory.episodic.interactions_db_path,
        auto_backup_interval_minutes=config.memory.episodic.auto_backup_interval_minutes,
    )

    try:
        await logger.connect()

        # Execute command
        if args.command == "recent":
            await view_recent(logger, n=args.n, role=args.role)
        elif args.command == "search":
            await search(logger, args.query, limit=args.limit)
        elif args.command == "session":
            await view_session(logger, args.session_id)
        elif args.command == "export-all":
            await export_all(logger, args.output)
        elif args.command == "export-session":
            await export_session(logger, args.session_id, args.output)
        elif args.command == "stats":
            await stats(logger)
        elif args.command == "backup":
            await backup(logger)

    finally:
        # Close without creating another backup (we just want to disconnect)
        if logger._db:
            await logger._db.close()


if __name__ == "__main__":
    asyncio.run(main())
