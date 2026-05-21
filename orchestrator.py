import json
from datetime import datetime
from pathlib import Path

import anthropic
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

import config
from agents.research import ResearchAgent
from agents.writer import WriterAgent
from agents.editor import EditorAgent
from storage.db import (
    get_next_topic, get_topic_by_id, get_pending_drafts,
    get_latest_draft_for_topic, approve_draft, reject_draft
)

console = Console()


def _client():
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def run_research():
    console.print("\n[bold blue]Research Agent[/bold blue] — finding topics...")
    ResearchAgent(_client()).run_research()
    console.print("[green]Done. Topics saved to queue.[/green]")


def run_write(topic_id: int = None):
    topic = get_topic_by_id(topic_id) if topic_id else get_next_topic()
    if not topic:
        console.print("[yellow]No queued topics. Run: python main.py research[/yellow]")
        return

    console.print(f"\n[bold]Topic:[/bold] {topic['title']}")
    console.print(f"[dim]Keyword: {topic['keyword']} | Source: {topic['source']}[/dim]\n")

    console.print("[bold blue]Writer Agent[/bold blue] — writing article...")
    WriterAgent(_client()).write_article(topic)

    draft = get_latest_draft_for_topic(topic["id"])
    if not draft:
        console.print("[red]Writer did not save a draft. Check API key and try again.[/red]")
        return

    draft["keyword"] = topic["keyword"]
    draft["research_brief"] = topic.get("research_brief", "")

    console.print("[bold blue]Editor Agent[/bold blue] — reviewing and editing...")
    EditorAgent(_client()).edit_article(draft)

    console.print(f"\n[green]Article ready for review.[/green] Run: python main.py review")


def run_review():
    pending = get_pending_drafts()
    if not pending:
        console.print("[yellow]No articles pending review.[/yellow]")
        return

    console.print(f"\n[bold]{len(pending)} article(s) awaiting review[/bold]\n")

    for draft in pending:
        console.rule(f"[bold]{draft['title']}[/bold]")
        console.print(f"[dim]Keyword:[/dim] {draft['keyword']}")
        console.print(f"[dim]Slug:[/dim] {draft['slug']}")
        console.print(f"[dim]Tags:[/dim] {', '.join(draft['tags'])}")
        console.print(f"[dim]Meta:[/dim] {draft['meta_description']}\n")

        if draft.get("edit_notes"):
            console.print(Panel(draft["edit_notes"], title="[yellow]Editor notes[/yellow]", border_style="yellow", padding=(0, 1)))

        console.print(Panel(Markdown(draft["content"]), title="[blue]Article preview[/blue]", border_style="blue"))

        choice = Prompt.ask(
            "\n[bold]Action[/bold]",
            choices=["a", "r", "s"],
            default="s",
            show_default=False,
            prompt_suffix=" → [a]pprove  [r]eject  [s]kip: ",
        )

        if choice == "a":
            approved = approve_draft(draft["id"])
            path = _save_output(approved)
            console.print(f"[green]Approved →[/green] {path}\n")
        elif choice == "r":
            reject_draft(draft["id"])
            console.print("[red]Rejected.[/red]\n")
        else:
            console.print("[dim]Skipped.[/dim]\n")


def run_pipeline():
    from storage.db import get_all_topics
    queued = get_all_topics(status="queued")
    if not queued:
        run_research()
    run_write()
    run_review()


def _save_output(draft: dict) -> str:
    output_dir = Path(config.OUTPUT_DIR)
    output_dir.mkdir(exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    slug = draft.get("slug") or "post"
    filename = f"{date_str}-{slug}.md"

    tags = draft.get("tags", [])
    if isinstance(tags, str):
        tags = json.loads(tags)
    tags_yaml = "[" + ", ".join(f'"{t}"' for t in tags) + "]"

    title = (draft.get("title") or "").replace('"', '\\"')
    description = (draft.get("meta_description") or "").replace('"', '\\"')

    frontmatter = f"""---
title: "{title}"
date: "{date_str}"
slug: "{slug}"
description: "{description}"
tags: {tags_yaml}
status: published
---

"""

    filepath = output_dir / filename
    filepath.write_text(frontmatter + draft["content"])
    return str(filepath)
