import json
import os
import uuid
import time
from datetime import datetime

from storage.db import (
    create_agent_run, finish_agent_run, log_tool_call as _db_log_tool,
    get_tool_calls_for_run, log_agent_iteration,
)

# Large article bodies — stored as preview + char count, not full text
_CONTENT_KEYS = {"content", "original_content", "refreshed_content"}
# edit_notes and research_brief are intentionally NOT redacted — they explain what happened


def _detect_trigger() -> str:
    return "actions" if os.getenv("GITHUB_ACTIONS") else "manual"


def _sanitize_inputs(inputs: dict) -> dict:
    """Keep all fields visible; for large content, store preview + char count."""
    result = {}
    for k, v in inputs.items():
        v_str = str(v)
        if k in _CONTENT_KEYS:
            preview = v_str[:400]
            ellipsis = "…" if len(v_str) > 400 else ""
            result[k] = f"{preview}{ellipsis}  [{len(v_str)} chars total]"
        else:
            result[k] = v
    return result


def _sanitize_result(result) -> object:
    """For result dicts, preview large content fields."""
    if not isinstance(result, dict):
        return result
    out = {}
    for k, v in result.items():
        v_str = str(v)
        if k in _CONTENT_KEYS and len(v_str) > 200:
            out[k] = f"{v_str[:200]}…  [{len(v_str)} chars total]"
        else:
            out[k] = v
    return out


def _result_preview(result) -> str:
    if result is None:
        return "null"
    if isinstance(result, dict):
        if "error" in result:
            return f"ERROR: {result['error'][:120]}"
        if result.get("skipped"):
            return f"SKIPPED: {result.get('reason', '')[:100]}"
        if "success" in result and result["success"]:
            extras = {k: v for k, v in result.items()
                      if k not in ("success", "error") and k not in _CONTENT_KEYS}
            if extras:
                preview = ", ".join(f"{k}={repr(v)[:40]}" for k, v in list(extras.items())[:4])
                return f"ok — {preview}"
            return "ok"
        parts = []
        for k, v in list(result.items())[:4]:
            if k in _CONTENT_KEYS:
                parts.append(f"{k}=[{len(str(v))} chars]")
            elif isinstance(v, list):
                parts.append(f"{k}=[{len(v)} items]")
            else:
                parts.append(f"{k}={repr(str(v))[:40]}")
        return ", ".join(parts) or "{}"
    if isinstance(result, list):
        if len(result) == 0:
            return "[] (empty)"
        if isinstance(result[0], dict) and "error" in result[0]:
            return f"ERROR: {result[0]['error'][:100]}"
        return f"[{len(result)} items]"
    return str(result)[:120]


def _quality_signal(tool_name: str, inputs: dict, result) -> str:
    """Classify the quality/outcome of a tool call result."""
    if isinstance(result, dict) and "error" in result:
        return "error"
    if isinstance(result, list) and result and isinstance(result[0], dict) and "error" in result[0]:
        return "error"
    if isinstance(result, dict) and result.get("skipped"):
        return "skipped"

    _gsc_ga4 = {"get_gsc_queries", "get_gsc_rising", "get_ga4_top_pages", "get_ga4_declining"}
    if isinstance(result, list) and len(result) == 0:
        return "no_data" if tool_name in _gsc_ga4 else "empty"

    if tool_name in ("web_search", "analyze_serp", "discover_keywords", "get_google_trends"):
        if isinstance(result, list) and len(result) < 3:
            return "sparse"

    if tool_name == "check_competitor_new_posts":
        if isinstance(result, dict) and result.get("new_count", 1) == 0:
            return "no_new"

    return "ok"


# ── Per-agent run summaries ────────────────────────────────────────────────────

def _build_run_summary(run_id: str, agent_name: str) -> str:
    try:
        tool_calls = get_tool_calls_for_run(run_id)
        if not tool_calls:
            return ""
        builders = {
            "research": _research_summary,
            "editor": _editor_summary,
            "writer": _writer_summary,
            "strategy": _strategy_summary,
        }
        fn = builders.get(agent_name)
        if fn:
            return fn(tool_calls)
        errors = sum(1 for tc in tool_calls if not tc["success"])
        tools = list(dict.fromkeys(tc["tool_name"] for tc in tool_calls))
        return f"{len(tool_calls)} steps: {', '.join(tools[:6])}" + (f" — {errors} errors" if errors else "")
    except Exception:
        return ""


def _research_summary(tool_calls: list) -> str:
    saved, skipped = [], []
    sources: set = set()
    source_map = {
        "web_search": "web", "get_gsc_queries": "GSC", "get_gsc_rising": "GSC",
        "get_ga4_top_pages": "GA4", "get_ga4_declining": "GA4",
        "check_competitor_new_posts": "competitors", "discover_keywords": "keywords",
        "get_google_trends": "trends", "analyze_serp": "SERP", "analyze_post": "competitor post",
    }
    for tc in tool_calls:
        src = source_map.get(tc["tool_name"])
        if src:
            sources.add(src)
        if tc["tool_name"] == "save_topic":
            try:
                result = json.loads(tc.get("result_json") or "{}")
                inputs = json.loads(tc.get("inputs_json") or "{}")
                title = inputs.get("title", "?")
                if result.get("skipped"):
                    skipped.append(title)
                elif result.get("success"):
                    angle = inputs.get("content_angle", "")
                    pillar = inputs.get("pillar_name", "")
                    tag = f" [{angle}/{pillar}]" if angle and pillar else (f" [{angle}]" if angle else "")
                    saved.append(f"{title}{tag}")
            except Exception:
                pass
    save_topic_calls = sum(1 for tc in tool_calls if tc["tool_name"] == "save_topic")
    if save_topic_calls == 0:
        return f"WARNING: 0 topics saved ({len(tool_calls)} steps — save_topic never called)"

    parts = []
    if saved:
        parts.append(f"Saved {len(saved)} topic(s): {'; '.join(saved)}")
    if skipped:
        parts.append(f"Skipped {len(skipped)} duplicate(s): {', '.join(skipped)}")
    if sources:
        parts.append(f"Sources used: {', '.join(sorted(sources))}")
    return " | ".join(parts) or f"{len(tool_calls)} steps"


def _editor_summary(tool_calls: list) -> str:
    for tc in tool_calls:
        if tc["tool_name"] == "save_edited_draft":
            try:
                inputs = json.loads(tc.get("inputs_json") or "{}")
                result = json.loads(tc.get("result_json") or "{}")
                word_count = result.get("word_count") or 0
                edit_notes = inputs.get("edit_notes", "")
                notes_preview = edit_notes[:250] + ("…" if len(edit_notes) > 250 else "")
                title = inputs.get("title", "")
                parts = []
                if word_count:
                    parts.append(f"{word_count:,} words")
                if title:
                    parts.append(f"title updated → '{title}'")
                if notes_preview:
                    parts.append(f"Changes: {notes_preview}")
                return " | ".join(parts) if parts else "Draft saved"
            except Exception:
                pass
    return f"{len(tool_calls)} steps"


def _writer_summary(tool_calls: list) -> str:
    for tc in tool_calls:
        if tc["tool_name"] == "save_draft":
            try:
                inputs = json.loads(tc.get("inputs_json") or "{}")
                result = json.loads(tc.get("result_json") or "{}")
                word_count = result.get("word_count") or 0
                slug = inputs.get("slug", "")
                title = inputs.get("title", "")
                searches = sum(1 for t in tool_calls if t["tool_name"] == "web_search")
                parts = [f"Wrote article"]
                if title:
                    parts.append(f"'{title}'")
                if word_count:
                    parts.append(f"{word_count:,} words")
                if slug:
                    parts.append(f"slug: {slug}")
                if searches:
                    parts.append(f"{searches} web search(es) for facts")
                return " | ".join(parts)
            except Exception:
                pass
    return f"{len(tool_calls)} steps"


def _strategy_summary(tool_calls: list) -> str:
    for tc in tool_calls:
        if tc["tool_name"] == "save_strategy":
            try:
                inputs = json.loads(tc.get("inputs_json") or "{}")
                pillars = inputs.get("content_pillars", [])
                competitors = inputs.get("competitors", [])
                gaps = inputs.get("content_gaps", [])
                wins = inputs.get("quick_wins", [])
                pillar_names = [p.get("name", "") for p in pillars[:4]]
                return (
                    f"Built strategy: {len(pillars)} pillars ({', '.join(pillar_names)}), "
                    f"{len(competitors)} competitors, "
                    f"{len(gaps)} content gaps, {len(wins)} quick wins"
                )
            except Exception:
                pass
    return f"{len(tool_calls)} steps"


# ── RunContext ─────────────────────────────────────────────────────────────────

class RunContext:
    def __init__(self, agent_name: str, topic_id: int = None, topic_title: str = None):
        self.run_id = uuid.uuid4().hex[:12]
        self.agent_name = agent_name
        self.topic_id = topic_id
        self.topic_title = topic_title
        self._started_at = datetime.now().isoformat()
        self._start_mono = time.monotonic()
        self._iterations = 0
        self._tokens_input = 0
        self._tokens_output = 0
        self._seq = 0
        self._error: str | None = None

    def __enter__(self):
        create_agent_run(
            run_id=self.run_id,
            agent_name=self.agent_name,
            started_at=self._started_at,
            topic_id=self.topic_id,
            topic_title=self.topic_title,
            trigger=_detect_trigger(),
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self._error = f"{exc_type.__name__}: {exc_val}"
        status = "failed" if self._error else "success"
        run_summary = _build_run_summary(self.run_id, self.agent_name)
        finish_agent_run(
            run_id=self.run_id,
            status=status,
            finished_at=datetime.now().isoformat(),
            duration_seconds=round(time.monotonic() - self._start_mono, 2),
            iterations=self._iterations,
            tokens_input=self._tokens_input,
            tokens_output=self._tokens_output,
            error_message=self._error,
            run_summary=run_summary,
        )
        return False

    @property
    def current_iteration(self) -> int:
        return self._iterations

    def mark_failed(self, error: str) -> None:
        self._error = error

    def increment_iteration(self) -> None:
        self._iterations += 1

    def add_tokens(self, inp: int, out: int) -> None:
        self._tokens_input += inp
        self._tokens_output += out

    def log_iteration(self, tokens_input: int, tokens_output: int, stop_reason: str,
                      assistant_preview: str, tool_names: list,
                      started_at: str, duration_ms: int) -> None:
        log_agent_iteration(
            run_id=self.run_id,
            iteration_num=self._iterations,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            stop_reason=stop_reason,
            assistant_preview=assistant_preview,
            tool_names=tool_names,
            started_at=started_at,
            duration_ms=duration_ms,
        )

    def log_tool_call(self, tool_name: str, inputs: dict, result,
                      duration_ms: int, error: str = None) -> None:
        self._seq += 1
        success = error is None and not (isinstance(result, dict) and "error" in result)
        if not success and error is None and isinstance(result, dict):
            error = result.get("error")

        signal = _quality_signal(tool_name, inputs, result)
        if not success:
            signal = "error"

        inputs_safe = _sanitize_inputs(inputs)
        result_safe = _sanitize_result(result)

        _db_log_tool(
            run_id=self.run_id,
            seq_num=self._seq,
            tool_name=tool_name,
            inputs_json=json.dumps(inputs_safe, default=str)[:6000],
            result_json=json.dumps(result_safe, default=str)[:4000],
            result_preview=_result_preview(result)[:300],
            success=success,
            error_message=error,
            started_at=datetime.now().isoformat(),
            duration_ms=duration_ms,
            quality_signal=signal,
            iteration_num=self._iterations,
        )
