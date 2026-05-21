import json
import subprocess
import os
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt

import config
from agents.research import ResearchAgent
from agents.writer import WriterAgent
from agents.editor import EditorAgent
from agents.strategy import StrategyAgent
from storage.db import (
    get_next_topic, get_topic_by_id, get_pending_drafts,
    get_latest_draft_for_topic, approve_draft, reject_draft,
    get_active_strategy, save_strategy,
)

console = Console()


def _client():
    """Return the appropriate API client based on configured provider."""
    if config.PROVIDER == "groq":
        from openai import OpenAI
        if not config.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY not set in .env")
        return OpenAI(api_key=config.GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
    elif config.PROVIDER == "ollama":
        from openai import OpenAI
        return OpenAI(api_key="ollama", base_url=config.OLLAMA_BASE_URL)
    else:
        import anthropic
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

    # Re-fetch the edited draft
    edited = get_latest_draft_for_topic(topic["id"])
    if not edited:
        console.print("[red]Editor did not save draft.[/red]")
        return

    if config.APPROVAL_MODE == "pr":
        pr_url = _create_pr(edited)
        if pr_url:
            console.print(f"\n[green]PR created →[/green] {pr_url}")
            console.print("[dim]Review in Cursor or GitHub. Merge = publish. Close = reject.[/dim]")
        else:
            console.print(f"\n[green]Article ready for review.[/green] Run: python main.py review")
    else:
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


def run_strategy(force: bool = False):
    existing = get_active_strategy()
    if existing and not force:
        console.print("\n[yellow]An active strategy already exists.[/yellow]")
        console.print(f"[dim]Created: {existing['created_at']}[/dim]")
        console.print(f"[dim]Pillars: {', '.join(p['name'] for p in existing['content_pillars'])}[/dim]")
        choice = Prompt.ask(
            "\nReplace it with a new strategy?",
            choices=["y", "n"],
            default="n",
        )
        if choice != "y":
            return

    console.print()
    console.rule("[bold blue]Blogging Strategy Setup[/bold blue]")
    console.print(
        "\nI'll ask 6 quick questions, then research your competitive landscape\n"
        "and build a full content strategy. Takes about 3–5 minutes.\n"
    )

    niche = Prompt.ask("[bold][1/6][/bold] What is your blog about?\n      [dim](Be specific — include niche, angle, and what makes it different)[/dim]\n     ")

    console.print("\n[bold][2/6][/bold] What is your primary goal?")
    console.print("      1. Grow organic SEO traffic")
    console.print("      2. Generate leads for a product/service")
    console.print("      3. Build brand authority / thought leadership")
    console.print("      4. Monetization (ads, affiliates, sponsorships)")
    goal_num = IntPrompt.ask("     ", default=1)
    goal_map = {1: "organic SEO traffic", 2: "lead generation", 3: "brand authority", 4: "monetization"}
    goal = goal_map.get(goal_num, "organic SEO traffic")

    target_reader = Prompt.ask(
        "\n[bold][3/6][/bold] Describe your target reader in one sentence\n      [dim](job title, situation, what they're trying to solve)[/dim]\n     "
    )

    desired_action = Prompt.ask(
        "\n[bold][4/6][/bold] What action should readers take after reading?\n      [dim](subscribe, book a call, buy X, share, etc.)[/dim]\n     "
    )

    avoid = Prompt.ask(
        "\n[bold][5/6][/bold] Any topics, angles, or keywords to explicitly avoid?\n      [dim](Press Enter to skip)[/dim]\n     ",
        default="",
    )

    console.print("\n[bold][6/6][/bold] Publishing frequency?")
    console.print("      1. Weekly")
    console.print("      2. Twice a week")
    console.print("      3. Daily")
    console.print("      4. Bi-weekly")
    freq_num = IntPrompt.ask("     ", default=1)
    freq_map = {1: "weekly", 2: "twice a week", 3: "daily", 4: "bi-weekly"}
    frequency = freq_map.get(freq_num, "weekly")

    interview = {
        "niche": niche,
        "goal": goal,
        "target_reader": target_reader,
        "desired_action": desired_action,
        "avoid": avoid,
        "frequency": frequency,
    }

    console.print(f"\n[green]Got it.[/green] Researching your competitive landscape...\n")
    console.print("[dim]This will search DuckDuckGo, scrape competitor sitemaps, and analyse keyword clusters.[/dim]\n")

    agent = StrategyAgent(_client())
    agent.build_strategy(interview)

    strategy = get_active_strategy()
    if not strategy:
        console.print("[red]Strategy agent did not save a strategy. Try again.[/red]")
        return

    _display_strategy(strategy)

    choice = Prompt.ask(
        "\n[bold]Approve this strategy?[/bold]",
        choices=["y", "n"],
        default="y",
        prompt_suffix=" [y]es / [n]o, discard: ",
    )

    if choice == "y":
        console.print("[green]Strategy saved. Research runs will now use this strategy.[/green]")
        console.print("Next: [bold]python main.py research[/bold]")
    else:
        # Deactivate
        from storage.db import get_conn
        with get_conn() as conn:
            conn.execute("UPDATE strategy SET is_active = 0 WHERE id = ?", (strategy["id"],))
        console.print("[yellow]Strategy discarded. Run 'python main.py strategy' again to rebuild.[/yellow]")


def _display_strategy(strategy: dict):
    console.print()
    console.rule("[bold]Strategy Summary[/bold]")

    pillars = strategy.get("content_pillars", [])
    if pillars:
        console.print("\n[bold]Content Pillars[/bold]")
        for p in pillars:
            kws = ", ".join(p.get("target_keywords", [])[:5])
            console.print(f"  [cyan]{p['name']}[/cyan] — {p.get('description', '')}")
            console.print(f"    [dim]Keywords: {kws}[/dim]")

    competitors = strategy.get("competitors", [])
    if competitors:
        console.print("\n[bold]Competitors to Monitor[/bold]")
        for c in competitors:
            console.print(f"  [yellow]{c.get('name', c.get('url', ''))}[/yellow] — {c.get('focus', '')} [dim]({c.get('url', '')})[/dim]")

    gaps = strategy.get("content_gaps", [])
    if gaps:
        console.print(f"\n[bold]Content Gaps[/bold] [dim](topics competitors rank for that you don't cover)[/dim]")
        for g in gaps[:6]:
            console.print(f"  · {g}")

    wins = strategy.get("quick_wins", [])
    if wins:
        console.print(f"\n[bold]Quick Wins[/bold] [dim](low-competition keywords to target first)[/dim]")
        for w in wins[:6]:
            console.print(f"  · {w}")

    if strategy.get("strategic_summary"):
        console.print(Panel(strategy["strategic_summary"], title="[green]Strategic rationale[/green]", border_style="green", padding=(0, 1)))


def _create_pr(draft: dict) -> str | None:
    """
    Write the article to CONTENT_DIR on a new branch and open a GitHub PR.
    Merge the PR to approve (Vercel auto-deploys). Close to reject.
    Returns the PR URL, or None if git/gh is not available.
    """
    repo_dir = Path(config.REPO_DIR).resolve() if config.REPO_DIR else Path.cwd()
    date_str = datetime.now().strftime("%Y-%m-%d")
    slug = draft.get("slug") or "post"
    branch = f"blog/{date_str}-{slug}"

    def git(*args):
        return subprocess.run(["git", *args], cwd=repo_dir, capture_output=True, text=True, check=True)

    try:
        # Remember current branch so we can return to it
        current = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

        git("checkout", "-b", branch)

        content_dir = repo_dir / config.CONTENT_DIR
        content_dir.mkdir(parents=True, exist_ok=True)
        filepath = content_dir / f"{date_str}-{slug}.md"
        filepath.write_text(_build_markdown(draft))

        git("add", str(filepath))
        git("commit", "-m", f"blog: {draft['title']}")
        git("push", "-u", "origin", branch)

        pr_body = _build_pr_body(draft)
        result = subprocess.run(
            ["gh", "pr", "create",
             "--title", draft["title"],
             "--body", pr_body,
             "--base", "main"],
            cwd=repo_dir, capture_output=True, text=True
        )
        pr_url = result.stdout.strip() if result.returncode == 0 else None

        git("checkout", current)
        return pr_url

    except subprocess.CalledProcessError as e:
        console.print(f"[yellow]Git/PR step failed: {e.stderr.strip() or e}[/yellow]")
        console.print("[dim]Falling back to local save. Run: python main.py review[/dim]")
        try:
            git("checkout", current)
        except Exception:
            pass
        return None


def _build_pr_body(draft: dict) -> str:
    tags = draft.get("tags", [])
    if isinstance(tags, str):
        tags = json.loads(tags)
    preview = (draft.get("content") or "")[:400].strip()

    edit_notes_section = ""
    if draft.get("edit_notes"):
        edit_notes_section = f"\n### Editor notes\n{draft['edit_notes']}\n"

    return f"""**Keyword:** `{draft.get('keyword', '')}`
**Slug:** `{draft.get('slug', '')}`
**Tags:** {', '.join(tags)}

**Meta description:**
> {draft.get('meta_description', '')}
{edit_notes_section}
---

### Article preview
{preview}…

---
*Generated by [Blogging Agent](https://github.com/vipulawl/blogging-agent) · Merge to publish · Close to reject*"""


def _build_markdown(draft: dict) -> str:
    date_str = datetime.now().strftime("%Y-%m-%d")
    slug = draft.get("slug") or "post"
    tags = draft.get("tags", [])
    if isinstance(tags, str):
        tags = json.loads(tags)
    tags_yaml = "[" + ", ".join(f'"{t}"' for t in tags) + "]"
    title = (draft.get("title") or "").replace('"', '\\"')
    description = (draft.get("meta_description") or "").replace('"', '\\"')

    return f"""---
title: "{title}"
date: "{date_str}"
slug: "{slug}"
description: "{description}"
tags: {tags_yaml}
status: published
---

{draft['content']}"""


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
