import json
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich.rule import Rule
from rich.markup import escape

from storage.db import (
    get_agent_runs, get_agent_run_by_id, get_tool_calls_for_run,
    get_agent_stats, get_tool_stats, get_iterations_for_run,
)

console = Console()

_AGENT_COLORS = {
    "research": "cyan", "writer": "blue", "editor": "magenta",
    "strategy": "yellow", "refresh": "orange3", "corrector": "red",
    "base": "white",
}


def _agent_color(name: str) -> str:
    return _AGENT_COLORS.get(name.lower(), "white")


def _status_text(status: str) -> Text:
    if status == "success":
        return Text("✓ success", style="green")
    if status == "failed":
        return Text("✗ failed", style="bold red")
    if status == "running":
        return Text("⟳ running", style="yellow")
    return Text(status, style="dim")


def _fmt_duration(seconds) -> str:
    if seconds is None:
        return "—"
    seconds = float(seconds)
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s"


def _fmt_ms(ms) -> str:
    if ms is None:
        return "—"
    ms = int(ms)
    return f"{ms / 1000:.2f}s" if ms >= 1000 else f"{ms}ms"


def _fmt_ts(ts: str) -> str:
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ts[:19]


def _pretty_json(json_str: str, max_lines: int = 25) -> str:
    if not json_str:
        return ""
    try:
        obj = json.loads(json_str)
        lines = json.dumps(obj, indent=2, default=str).splitlines()
        if len(lines) > max_lines:
            lines = lines[:max_lines] + [f"  ... ({len(lines) - max_lines} more lines)"]
        return "\n".join(lines)
    except Exception:
        return (json_str or "")[:600]


def _format_inputs_compact(inputs_json: str) -> str:
    """Format inputs for the compact table view."""
    if not inputs_json:
        return ""
    try:
        inp = json.loads(inputs_json)
        parts = []
        for k, v in list(inp.items())[:4]:
            v_str = str(v)
            truncated = (v_str[:55] + "…") if len(v_str) > 55 else v_str
            parts.append(f"{escape(k)}={escape(repr(truncated))}")
        suffix = f"  [dim]+{len(inp) - 4} more[/dim]" if len(inp) > 4 else ""
        return "\n".join(parts) + suffix
    except Exception:
        return escape((inputs_json or "")[:200])


def show_recent(limit: int = 25, agent_name: str = None, failed_only: bool = False) -> None:
    status_filter = "failed" if failed_only else None
    runs = get_agent_runs(limit=limit, agent_name=agent_name, status=status_filter)

    title = "Recent Agent Runs"
    if agent_name:
        title += f" — {agent_name}"
    if failed_only:
        title += " (failures only)"

    console.print()

    if runs:
        total = len(runs)
        successes = sum(1 for r in runs if r["status"] == "success")
        failures = sum(1 for r in runs if r["status"] == "failed")
        running = sum(1 for r in runs if r["status"] == "running")
        completed = total - running
        pct = f"{successes / completed * 100:.0f}%" if completed else "—"
        avg_dur = (
            sum(r["duration_seconds"] or 0 for r in runs if r.get("duration_seconds"))
            / max(1, completed)
        )
        total_tokens = sum((r["tokens_input"] or 0) + (r["tokens_output"] or 0) for r in runs)

        fail_color = "red" if failures else "dim"
        panels = [
            Panel(f"[bold]{total}[/bold]\n[dim]runs shown[/dim]", expand=True, border_style="dim"),
            Panel(f"[bold green]{successes}[/bold green] [dim]({pct})[/dim]\n[dim]succeeded[/dim]", expand=True, border_style="green"),
            Panel(f"[bold {fail_color}]{failures}[/bold {fail_color}]\n[dim]failed[/dim]", expand=True, border_style=fail_color),
            Panel(f"[bold]{_fmt_duration(avg_dur)}[/bold]\n[dim]avg duration[/dim]", expand=True, border_style="dim"),
            Panel(f"[bold]{total_tokens:,}[/bold]\n[dim]total tokens[/dim]", expand=True, border_style="dim"),
        ]
        console.print(Columns(panels, equal=True, expand=True))
        console.print()

    table = Table(title=title, show_lines=False, border_style="dim")
    table.add_column("ID", style="dim", width=6, justify="right")
    table.add_column("Agent", width=12)
    table.add_column("Started", width=20)
    table.add_column("Duration", width=10, justify="right")
    table.add_column("Steps", width=6, justify="right")
    table.add_column("Tokens in/out", width=16, justify="right")
    table.add_column("Topic", max_width=30, no_wrap=True)
    table.add_column("Status", width=16)
    table.add_column("Trigger", width=8, style="dim")

    for r in runs:
        color = _agent_color(r["agent_name"])
        tokens = (
            f"{r['tokens_input']:,}/{r['tokens_output']:,}"
            if r["tokens_input"] or r["tokens_output"]
            else "—"
        )
        table.add_row(
            str(r["id"]),
            f"[{color}]{r['agent_name']}[/{color}]",
            _fmt_ts(r["started_at"]),
            _fmt_duration(r["duration_seconds"]),
            str(r["iterations"] or "—"),
            tokens,
            (r.get("topic_title") or "")[:30],
            _status_text(r["status"]),
            r.get("trigger", "manual"),
        )

    console.print(table)

    total = len(runs)
    successes = sum(1 for r in runs if r["status"] == "success")
    failures = sum(1 for r in runs if r["status"] == "failed")
    pct = f"{successes / total * 100:.0f}%" if total else "—"
    console.print(
        f"\n[dim]Showing {total} run(s)  |  "
        f"[green]{successes} success ({pct})[/green]  |  "
        f"[{'red' if failures else 'dim'}]{failures} failed[/{'red' if failures else 'dim'}][/dim]"
    )
    if runs:
        console.print("[dim]Detail:  python main.py logs --run <ID>[/dim]")
        console.print("[dim]Full JSON: python main.py logs --run <ID> --full[/dim]\n")


_QUALITY_STYLES = {
    "ok":      ("✓", "green"),
    "skipped": ("⊘", "yellow"),
    "empty":   ("○", "yellow"),
    "sparse":  ("◔", "yellow"),
    "no_data": ("–", "dim"),
    "no_new":  ("–", "dim"),
    "warn":    ("⚠", "yellow"),
    "error":   ("✗", "red"),
}


def _quality_badge(signal: str) -> Text:
    icon, style = _QUALITY_STYLES.get(signal or "ok", ("?", "dim"))
    return Text(f"{icon} {signal or 'ok'}", style=style)


def show_run_detail(run_id_or_db_id: str, full: bool = False) -> None:
    run = get_agent_run_by_id(run_id_or_db_id)
    if not run:
        runs = get_agent_runs(limit=1000)
        run = next((r for r in runs if str(r["id"]) == str(run_id_or_db_id)), None)
    if not run:
        console.print(f"[red]Run not found: {run_id_or_db_id}[/red]")
        return

    color = _agent_color(run["agent_name"])
    is_failed = run["status"] == "failed"

    console.print()
    console.rule(
        f"[bold]Run #{run['id']} — [{color}]{run['agent_name']}[/{color}]  "
        f"{_status_text(run['status'])}[/bold]"
    )
    console.print()

    # ── Run summary ───────────────────────────────────────────────────────────────
    summary = run.get("run_summary") or ""
    if summary:
        console.print(Panel(
            escape(summary),
            title="[bold]Run Summary[/bold]",
            border_style=color,
            padding=(0, 2),
        ))
        console.print()

    # ── Metadata panels ──────────────────────────────────────────────────────────
    left_lines = [
        f"[dim]Started:[/dim]   {_fmt_ts(run['started_at'])}",
        f"[dim]Finished:[/dim]  {_fmt_ts(run.get('finished_at', ''))}",
        f"[dim]Duration:[/dim]  {_fmt_duration(run.get('duration_seconds'))}",
        f"[dim]Trigger:[/dim]   {run.get('trigger', 'manual')}",
    ]
    if run.get("topic_title"):
        left_lines.append(f"[dim]Topic:[/dim]     {escape(run['topic_title'])}")
    if run.get("topic_id"):
        left_lines.append(f"[dim]Topic ID:[/dim]  {run['topic_id']}")

    right_lines = [
        f"[bold]{run.get('iterations', 0) or 0}[/bold]  [dim]iterations / cycles[/dim]",
    ]
    if run.get("tokens_input") or run.get("tokens_output"):
        right_lines.append(
            f"[bold]{run.get('tokens_input', 0):,}[/bold] [dim]tokens in[/dim]"
        )
        right_lines.append(
            f"[bold]{run.get('tokens_output', 0):,}[/bold] [dim]tokens out[/dim]"
        )
    right_lines.append(f"[dim]Run ID:[/dim]  {run['run_id']}")

    console.print(Columns([
        Panel("\n".join(left_lines), title="[dim]Run Info[/dim]", border_style="dim", expand=True),
        Panel("\n".join(right_lines), title="[dim]Usage[/dim]", border_style="dim", expand=True),
    ], expand=True))

    # ── Failure panel ─────────────────────────────────────────────────────────────
    if is_failed and run.get("error_message"):
        console.print()
        console.print(Panel(
            f"[bold red]{escape(run['error_message'])}[/bold red]",
            title="[bold red]✗  Run Failed[/bold red]",
            border_style="red",
            padding=(1, 2),
        ))

    # ── Tool calls ────────────────────────────────────────────────────────────────
    tool_calls = get_tool_calls_for_run(run["run_id"])
    if not tool_calls:
        console.print("\n  [dim](no tool calls recorded for this run)[/dim]\n")
        return

    failed_steps = [tc for tc in tool_calls if not tc["success"]]
    total_tool_ms = sum(tc.get("duration_ms") or 0 for tc in tool_calls)
    iterations = get_iterations_for_run(run["run_id"])

    if iterations:
        _show_merged_timeline(run, tool_calls, iterations, full=full)
    else:
        console.print()
        console.rule(
            f"[dim]Step Trace — {len(tool_calls)} steps"
            + (f"  •  [red]{len(failed_steps)} failed[/red]" if failed_steps else "")
            + f"  •  {_fmt_ms(total_tool_ms)} in tools[/dim]"
        )
        console.print()

        if full:
            for tc in tool_calls:
                _print_tool_call_panel(tc)
        else:
            table = Table(show_lines=True, border_style="dim", expand=True)
            table.add_column("#", width=5, justify="right")
            table.add_column("Tool", width=28)
            table.add_column("Signal", width=14)
            table.add_column("Time", width=8, justify="right")
            table.add_column("Inputs", min_width=28)
            table.add_column("Result / Error", min_width=32)

            for tc in tool_calls:
                ok = tc["success"]
                signal = tc.get("quality_signal") or ("error" if not ok else "ok")
                seq_cell = Text(f"{'✓' if ok else '✗'} {tc['seq_num']}", style="green" if ok else "bold red")
                tool_cell = Text(tc["tool_name"], style="green" if ok else "red")

                if not ok:
                    err = tc.get("error_message") or (tc.get("result_preview") or "error")
                    result_cell = Text(f"ERROR: {err[:120]}", style="red")
                else:
                    result_cell = Text((tc.get("result_preview") or "")[:120])

                table.add_row(
                    seq_cell,
                    tool_cell,
                    _quality_badge(signal),
                    _fmt_ms(tc.get("duration_ms")),
                    _format_inputs_compact(tc.get("inputs_json")),
                    result_cell,
                )

            console.print(table)

    # ── Edit notes panel (for editor runs) ────────────────────────────────────────
    for tc in tool_calls:
        if tc["tool_name"] == "save_edited_draft" and tc["success"]:
            _print_edit_notes_panel(tc)
            break

    # ── Failed step detail panels ─────────────────────────────────────────────────
    if failed_steps:
        console.print()
        console.rule(f"[bold red]Failed Steps — {len(failed_steps)} of {len(tool_calls)}[/bold red]")
        console.print()
        for tc in failed_steps:
            err_msg = tc.get("error_message") or (tc.get("result_preview") or "unknown error")
            body_lines = [
                f"[dim]Duration:[/dim] {_fmt_ms(tc.get('duration_ms'))}  "
                f"[dim]|[/dim]  [dim]At:[/dim] {_fmt_ts(tc.get('started_at', ''))}",
                "",
                f"[bold red]Error:[/bold red] {escape(err_msg)}",
            ]
            if tc.get("inputs_json"):
                pretty_in = _pretty_json(tc["inputs_json"], max_lines=20)
                body_lines += ["", "[dim]── Inputs ──[/dim]", escape(pretty_in)]
            if tc.get("result_json"):
                pretty_res = _pretty_json(tc["result_json"], max_lines=20)
                body_lines += ["", "[dim]── Result JSON ──[/dim]", escape(pretty_res)]

            console.print(Panel(
                "\n".join(body_lines),
                title=f"[red]✗ Step #{tc['seq_num']} — {escape(tc['tool_name'])}[/red]",
                border_style="red",
                padding=(0, 2),
            ))

    # ── Sub-optimal steps ─────────────────────────────────────────────────────────
    _SUBOPTIMAL = {"empty", "sparse", "skipped", "no_new"}
    suboptimal = [tc for tc in tool_calls if tc.get("quality_signal") in _SUBOPTIMAL]
    if suboptimal and not full:
        console.print()
        console.rule("[yellow]Sub-optimal Steps[/yellow]")
        console.print()
        for tc in suboptimal:
            sig = tc.get("quality_signal", "")
            icon, style = _QUALITY_STYLES.get(sig, ("?", "dim"))
            console.print(
                f"  [{style}]{icon}[/{style}] Step #{tc['seq_num']} [bold]{tc['tool_name']}[/bold] "
                f"— [{style}]{sig}[/{style}]: {escape(tc.get('result_preview') or '')} "
                f"[dim]({_fmt_ms(tc.get('duration_ms'))})[/dim]"
            )

    # ── Footer ────────────────────────────────────────────────────────────────────
    console.print()
    status_line = "[green]All steps succeeded[/green]" if not failed_steps else f"[red]{len(failed_steps)} step(s) failed[/red]"
    console.print(
        f"[dim]{len(tool_calls)} steps  •  {status_line}  •  "
        f"tool time: {_fmt_ms(total_tool_ms)}[/dim]"
    )
    if not full:
        console.print(f"[dim]Full JSON:  python main.py logs --run {run_id_or_db_id} --full[/dim]")
    console.print()


def _print_tool_call_panel(tc: dict) -> None:
    ok = tc["success"]
    border = "dim" if ok else "red"
    status_icon = "[green]✓[/green]" if ok else "[red]✗[/red]"

    body_lines = [
        f"[dim]Duration:[/dim] {_fmt_ms(tc.get('duration_ms'))}  "
        f"[dim]|[/dim]  [dim]Started:[/dim] {_fmt_ts(tc.get('started_at', ''))}",
    ]

    if not ok:
        err = tc.get("error_message") or (tc.get("result_preview") or "unknown error")
        body_lines += ["", f"[bold red]Error:[/bold red] {escape(err)}"]

    if tc.get("inputs_json"):
        pretty_in = _pretty_json(tc["inputs_json"], max_lines=30)
        body_lines += ["", "[dim]── Inputs ──[/dim]", escape(pretty_in)]

    if tc.get("result_json"):
        pretty_res = _pretty_json(tc["result_json"], max_lines=40)
        label = "[red]── Result (error) ──[/red]" if not ok else "[dim]── Result ──[/dim]"
        body_lines += ["", label, escape(pretty_res)]
    elif tc.get("result_preview"):
        body_lines += ["", "[dim]── Result ──[/dim]", escape(tc["result_preview"])]

    console.print(Panel(
        "\n".join(body_lines),
        title=f"{status_icon} [bold]Step #{tc['seq_num']}[/bold] — [{('red' if not ok else 'green')}]{escape(tc['tool_name'])}[/{'red' if not ok else 'green'}]",
        border_style=border,
        padding=(0, 1),
    ))
    console.print()


def _print_edit_notes_panel(tc: dict) -> None:
    """Render the editor's edit_notes and word count as a dedicated panel."""
    try:
        inputs = json.loads(tc.get("inputs_json") or "{}")
        result = json.loads(tc.get("result_json") or "{}")
        edit_notes = inputs.get("edit_notes", "")
        word_count = result.get("word_count") or 0
        title = inputs.get("title", "")
        meta = inputs.get("meta_description", "")

        lines = []
        if word_count:
            lines.append(f"[dim]Word count:[/dim] [bold]{word_count:,}[/bold]")
        if title:
            lines.append(f"[dim]Title updated:[/dim] {escape(title)}")
        if meta:
            lines.append(f"[dim]Meta updated:[/dim] {escape(meta)}")
        if lines:
            lines.append("")
        if edit_notes:
            lines.append("[dim]── Edit Notes ──[/dim]")
            lines.append(escape(edit_notes))
        else:
            lines.append("[dim](no edit_notes recorded)[/dim]")

        console.print()
        console.print(Panel(
            "\n".join(lines),
            title="[magenta]Editor Changes[/magenta]",
            border_style="magenta",
            padding=(0, 2),
        ))
    except Exception:
        pass


def _print_tool_call_inline(tc: dict) -> None:
    """One-line tool call for inside a merged-timeline turn block."""
    ok = tc["success"]
    signal = tc.get("quality_signal") or ("error" if not ok else "ok")
    icon, sig_style = _QUALITY_STYLES.get(signal or "ok", ("?", "dim"))

    try:
        inp = json.loads(tc.get("inputs_json") or "{}")
        kv = []
        for k, v in list(inp.items())[:3]:
            v_str = str(v)
            trunc = (v_str[:40] + "…") if len(v_str) > 40 else v_str
            kv.append(f"{k}={repr(trunc)}")
        extra = f" +{len(inp) - 3} more" if len(inp) > 3 else ""
        inputs_str = ", ".join(kv) + extra
    except Exception:
        inputs_str = ""

    result_str = ""
    if not ok:
        err = tc.get("error_message") or tc.get("result_preview") or "error"
        result_str = f" → [red]ERROR: {escape(str(err)[:80])}[/red]"
    elif tc.get("result_preview"):
        result_str = f" → [dim]{escape(tc['result_preview'][:80])}[/dim]"

    name_style = "red" if not ok else "green"
    console.print(
        f"    [{sig_style}]{icon}[/{sig_style}] "
        f"[{name_style}]step {tc['seq_num']}  {escape(tc['tool_name'])}[/{name_style}]"
        f"  [dim]({_fmt_ms(tc.get('duration_ms'))})[/dim]"
        f"  [dim]{escape(inputs_str[:70])}[/dim]"
        f"{result_str}"
    )


def _show_merged_timeline(run: dict, tool_calls: list, iterations: list, full: bool = False) -> None:
    """Interleave LLM reasoning turns and tool calls in chronological order."""
    color = _agent_color(run["agent_name"])

    # Group tool calls by the iteration that requested them
    iter_tools: dict[int, list] = {}
    for tc in tool_calls:
        n = tc.get("iteration_num") or 0
        iter_tools.setdefault(n, []).append(tc)

    n_total = len(iterations)
    failed_count = sum(1 for tc in tool_calls if not tc["success"])
    total_tool_ms = sum(tc.get("duration_ms") or 0 for tc in tool_calls)

    console.print()
    console.rule(
        f"[dim]Merged Timeline — {n_total} LLM turn(s)  •  {len(tool_calls)} tool call(s)"
        + (f"  •  [red]{failed_count} failed[/red]" if failed_count else "")
        + f"  •  {_fmt_ms(total_tool_ms)} in tools[/dim]"
    )

    for it in iterations:
        n = it["iteration_num"]
        tok_in = it.get("tokens_input") or 0
        tok_out = it.get("tokens_output") or 0
        stop = it.get("stop_reason") or ""
        dur = _fmt_ms(it.get("duration_ms"))

        stop_style = "green" if stop == "end_turn" else ("yellow" if stop == "tool_use" else "dim")

        console.print()
        console.rule(
            f"[{color}]Turn {n}/{n_total}[/{color}]  "
            f"[dim]{tok_in:,} in / {tok_out:,} out[/dim]  "
            f"[{stop_style}]{stop or '?'}[/{stop_style}]"
            f"[dim]  •  {dur}[/dim]",
            style="dim",
        )

        preview = (it.get("assistant_preview") or "").strip()
        if preview:
            console.print()
            console.print(Panel(
                escape(preview),
                title=f"[{color}]LLM reasoning[/{color}]",
                border_style=color,
                padding=(0, 2),
            ))

        turn_tools = iter_tools.get(n, [])
        if turn_tools:
            console.print()
            if full:
                for tc in turn_tools:
                    _print_tool_call_panel(tc)
            else:
                for tc in turn_tools:
                    _print_tool_call_inline(tc)

    # Orphaned tool calls (no matching iteration — can happen in partially-logged old data)
    orphans = iter_tools.get(0, [])
    if orphans:
        console.print()
        console.rule("[dim]Unattributed tool calls[/dim]")
        console.print()
        if full:
            for tc in orphans:
                _print_tool_call_panel(tc)
        else:
            for tc in orphans:
                _print_tool_call_inline(tc)


def show_stats() -> None:
    agent_stats = get_agent_stats()
    tool_stats = get_tool_stats(limit=12)

    console.print()
    console.rule("[bold]Agent Performance Stats[/bold]")
    console.print()

    if not agent_stats:
        console.print("[yellow]No completed runs yet.[/yellow]")
        return

    agent_table = Table(show_lines=False, border_style="dim")
    agent_table.add_column("Agent", width=14)
    agent_table.add_column("Runs", width=6, justify="right")
    agent_table.add_column("Success", width=8, justify="right")
    agent_table.add_column("Failed", width=7, justify="right")
    agent_table.add_column("Fail %", width=7, justify="right")
    agent_table.add_column("Avg Duration", width=14, justify="right")
    agent_table.add_column("Avg Steps", width=10, justify="right")
    agent_table.add_column("Total Tokens", width=14, justify="right")

    for s in agent_stats:
        color = _agent_color(s["agent_name"])
        total = s["total_runs"]
        fail_pct = (s["failures"] / total * 100) if total else 0
        fail_color = "red" if fail_pct > 10 else ("yellow" if fail_pct > 0 else "green")
        total_tokens = (s.get("total_tokens_input", 0) or 0) + (s.get("total_tokens_output", 0) or 0)
        agent_table.add_row(
            f"[{color}]{s['agent_name']}[/{color}]",
            str(total),
            f"[green]{s['successes']}[/green]",
            f"[{fail_color}]{s['failures']}[/{fail_color}]",
            f"[{fail_color}]{fail_pct:.0f}%[/{fail_color}]",
            _fmt_duration(s.get("avg_duration_seconds")),
            f"{s.get('avg_iterations', 0) or 0:.1f}",
            f"{total_tokens:,}" if total_tokens else "—",
        )

    console.print(agent_table)

    if tool_stats:
        console.print()
        console.rule("[bold]Most Used Tools[/bold]")
        console.print()

        tool_table = Table(show_lines=False, border_style="dim")
        tool_table.add_column("Tool", width=30)
        tool_table.add_column("Calls", width=7, justify="right")
        tool_table.add_column("Errors", width=7, justify="right")
        tool_table.add_column("Error %", width=8, justify="right")
        tool_table.add_column("Avg Time", width=10, justify="right")

        for t in tool_stats:
            total_calls = t["total_calls"]
            err_pct = (t["errors"] / total_calls * 100) if total_calls else 0
            err_color = "red" if err_pct > 10 else ("yellow" if err_pct > 0 else "dim")
            avg_ms = t.get("avg_duration_ms") or 0
            avg_str = f"{avg_ms / 1000:.2f}s" if avg_ms >= 100 else f"{int(avg_ms)}ms"
            tool_table.add_row(
                t["tool_name"],
                str(total_calls),
                f"[{err_color}]{t['errors']}[/{err_color}]",
                f"[{err_color}]{err_pct:.0f}%[/{err_color}]",
                avg_str,
            )

        console.print(tool_table)

    console.print()
