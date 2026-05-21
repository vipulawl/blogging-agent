import argparse
import sys

from rich.console import Console
from rich.table import Table

from storage.db import init_db

console = Console()


def cmd_research(_args):
    from orchestrator import run_research
    run_research()


def cmd_write(args):
    from orchestrator import run_write
    run_write(topic_id=getattr(args, "topic_id", None))


def cmd_review(_args):
    from orchestrator import run_review
    run_review()


def cmd_pipeline(_args):
    from orchestrator import run_pipeline
    run_pipeline()


def cmd_list_topics(_args):
    from storage.db import get_all_topics
    topics = get_all_topics()
    if not topics:
        console.print("[yellow]No topics yet. Run: python main.py research[/yellow]")
        return

    table = Table(title="Topics", show_lines=False)
    table.add_column("ID", style="dim", width=4)
    table.add_column("Title", max_width=55)
    table.add_column("Keyword", max_width=25)
    table.add_column("Source", width=10)
    table.add_column("Pri", width=4)
    table.add_column("Status", width=14)

    status_colors = {
        "queued": "cyan", "writing": "yellow", "editing": "yellow",
        "pending_approval": "green", "published": "blue",
        "rejected": "red", "approved": "blue",
    }
    for t in topics:
        color = status_colors.get(t["status"], "white")
        table.add_row(
            str(t["id"]),
            t["title"][:55],
            t["keyword"][:25],
            t["source"],
            f"{t['priority_score']:.1f}",
            f"[{color}]{t['status']}[/{color}]",
        )
    console.print(table)


def cmd_list_drafts(_args):
    from storage.db import get_pending_drafts
    drafts = get_pending_drafts()
    if not drafts:
        console.print("[yellow]No drafts pending review.[/yellow]")
        return

    table = Table(title="Pending Drafts")
    table.add_column("ID", style="dim", width=4)
    table.add_column("Title", max_width=55)
    table.add_column("Keyword", max_width=25)
    table.add_column("Status", width=10)

    for d in drafts:
        table.add_row(str(d["id"]), d["title"][:55], d["keyword"][:25], d["status"])
    console.print(table)


def main():
    init_db()

    parser = argparse.ArgumentParser(
        description="Blogging Agent — AI-powered content pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
commands:
  research      Run research agent — finds 3-5 topics and adds them to the queue
  write         Write + edit the highest-priority queued topic
  review        Review pending articles and approve/reject
  pipeline      research (if queue empty) → write → review
  list-topics   Show all topics and their status
  list-drafts   Show drafts awaiting your approval
        """,
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("research", help="Research new topics")

    write_p = subparsers.add_parser("write", help="Write + edit an article")
    write_p.add_argument("--topic-id", type=int, dest="topic_id", help="Specific topic ID (default: highest priority)")

    subparsers.add_parser("review", help="Review pending articles")
    subparsers.add_parser("pipeline", help="Full pipeline: research → write → review")
    subparsers.add_parser("list-topics", help="List all topics")
    subparsers.add_parser("list-drafts", help="List pending drafts")

    args = parser.parse_args()

    commands = {
        "research": cmd_research,
        "write": cmd_write,
        "review": cmd_review,
        "pipeline": cmd_pipeline,
        "list-topics": cmd_list_topics,
        "list-drafts": cmd_list_drafts,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
