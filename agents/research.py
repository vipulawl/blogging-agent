import config
from .base import BaseAgent
from tools.search import web_search
from tools.gsc import get_top_queries, get_rising_queries
from tools.ga4 import get_top_pages, get_declining_pages
from tools.serp import analyze_serp
from tools.competitors import get_sitemap_posts, fetch_post_summary
from tools.keyword_discovery import discover_keywords, get_google_trends
from storage.db import (
    save_topic, get_active_strategy, save_competitor_posts, get_pillar_coverage,
    record_sitemap_check, get_unreachable_competitors,
)

CONTENT_ANGLES = [
    "beginner-guide",
    "how-to",
    "comparison",
    "case-study",
    "deep-dive",
    "listicle",
    "tool-review",
    "faq",
    "opinion",
]

TOOLS = [
    {
        "name": "web_search",
        "description": "Search DuckDuckGo for trending topics, questions people ask, and competitor content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 8},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_gsc_queries",
        "description": "GSC: queries where you already appear — find low-CTR or position 5-20 opportunities. Returns [] if not configured.",
        "input_schema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "default": 28}},
        },
    },
    {
        "name": "get_gsc_rising",
        "description": "GSC: queries gaining impressions recently. Returns [] if not configured.",
        "input_schema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "default": 14}},
        },
    },
    {
        "name": "get_ga4_top_pages",
        "description": "GA4: top pages by sessions — understand what content format/topic already works. Returns [] if not configured.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 28},
                "limit": {"type": "integer", "default": 15},
            },
        },
    },
    {
        "name": "get_ga4_declining",
        "description": "GA4: pages losing traffic — candidates for refresh articles. Returns [] if not configured.",
        "input_schema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "default": 28}},
        },
    },
    {
        "name": "check_competitor_new_posts",
        "description": "Check a competitor's sitemap for posts published in the last N days that you haven't seen before. Use for each competitor in your strategy.",
        "input_schema": {
            "type": "object",
            "properties": {
                "site_url": {"type": "string"},
                "days_recent": {"type": "integer", "default": 14},
            },
            "required": ["site_url"],
        },
    },
    {
        "name": "analyze_post",
        "description": "Fetch a competitor post and extract title, H2 structure, word count. Use to understand what angle they took on a topic.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "analyze_serp",
        "description": "Check who ranks top-10 for a keyword. Use to gauge competition before recommending a topic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string"},
                "max_results": {"type": "integer", "default": 8},
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "discover_keywords",
        "description": "Expand a seed keyword with intent-based patterns (how to X, best X, X guide…) to find related keyword clusters not in GSC.",
        "input_schema": {
            "type": "object",
            "properties": {
                "seed_keyword": {"type": "string"},
                "max_patterns": {"type": "integer", "default": 5},
            },
            "required": ["seed_keyword"],
        },
    },
    {
        "name": "get_google_trends",
        "description": "Rising and top related queries from Google Trends for a topic.",
        "input_schema": {
            "type": "object",
            "properties": {"topic": {"type": "string"}},
            "required": ["topic"],
        },
    },
    {
        "name": "save_topic",
        "description": "Save a topic to the writing queue. Call for each of your 3-5 final recommendations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Specific, SEO-friendly article title"},
                "keyword": {"type": "string", "description": "Primary keyword"},
                "research_brief": {
                    "type": "string",
                    "description": "Brief for the writer: angle/hook, 4-6 subtopics, target reader pain point, competitor insight, suggested word count",
                },
                "pillar_name": {
                    "type": "string",
                    "description": "Exact name of the content pillar this topic belongs to (must match a pillar from the active strategy)",
                },
                "content_angle": {
                    "type": "string",
                    "description": f"Content angle for this post. Must be one of: {', '.join(CONTENT_ANGLES)}. Pick an angle NOT already covered for this pillar.",
                },
                "source": {"type": "string", "default": "web_search"},
                "priority_score": {"type": "number", "default": 0.5},
            },
            "required": ["title", "keyword", "research_brief", "pillar_name", "content_angle"],
        },
    },
]

SAVE_TOPIC_TOOL = TOOLS[-1]
SAVE_ONLY_TOOLS = [SAVE_TOPIC_TOOL]

SYSTEM = """You are an expert SEO research agent. Your job is to find 3-5 high-potential blog topics for this run.

MANDATORY COMPLETION RULE: You MUST call save_topic at least {min_topics} times before finishing. A text-only response without save_topic calls = failed run. Do NOT summarize findings — call save_topic.
TOOL BUDGET: max 3 check_competitor_new_posts, 2 discover_keywords, 3 analyze_serp, 1 get_google_trends — then STOP researching and call save_topic.

Blog niche: {niche}
Target audience: {audience}

── YOUR PRODUCT ────────────────────────────────────────────────────────────────
{product_summary}

Every topic you recommend must be relevant to a reader who would plausibly use this product.
Every research_brief must explain how the topic connects to the product's use cases or the problems it solves.
Do NOT recommend generic niche topics that have no connection to what the product does.

Active content strategy:
{strategy_context}

Pillar coverage (already written or in the pipeline — do NOT repeat these angles per pillar):
{pillar_coverage_context}

Content angle types (you MUST assign one per topic):
- beginner-guide: intro/fundamentals for newcomers
- how-to: step-by-step tutorial
- comparison: X vs Y or best alternatives
- case-study: real example or story
- deep-dive: advanced/comprehensive analysis
- listicle: list format (e.g. "10 ways to...")
- tool-review: review of a specific tool or product
- faq: question-answer format
- opinion: thought leadership or contrarian take

Angle diversity rules:
- Assign each topic to a pillar_name (must match an existing strategy pillar exactly)
- Choose a content_angle NOT already listed for that pillar in the coverage above
- Spread topics across DIFFERENT pillars in this run — do not queue 3 topics for the same pillar
- If all angles for a pillar are covered, pick the least-recently-used pillar with open angles

── COMPETITOR SITEMAP FAILURES (skip these — do NOT call check_competitor_new_posts for them) ──
{unreachable_context}

Research process for this run:
1. Check GSC (get_gsc_queries + get_gsc_rising) — find queries with impressions but low CTR or position 5-20
2. Check GA4 (get_ga4_top_pages + get_ga4_declining) — understand what's working and what needs a refresh
3. Check each competitor in the strategy for NEW posts (check_competitor_new_posts) — if they just published something in your content pillars, either counter it or find the angle they missed
4. For 1-2 competitor posts that look interesting, analyze_post to understand their angle and structure
5. For keywords NOT in GSC (i.e. topics you're not indexed for), use discover_keywords on pillar seed keywords
6. Use get_google_trends on 1-2 pillar topics to catch rising queries
7. Use analyze_serp to check competition level before committing to a topic
8. Save 3-5 topics with detailed research briefs — DO NOT finish without calling save_topic

Topic selection priority:
- Competitor just posted on a pillar topic → counter with a better/different angle
- GSC: high impressions, position 5-20, low CTR → strong signal
- Content gap from strategy + low SERP competition → good long-term bet
- Rising Google Trends query in your pillar → early mover advantage
- GA4 declining page → refresh opportunity (easier than new content)

For each research_brief include:
- Main angle/hook (what makes this different from what competitors already wrote)
- 4-6 subtopics/sections
- Target reader pain point
- Competitive insight (who ranks, their weakness)
- Suggested word count (800-2500)"""

SAVE_ONLY_SYSTEM = """You are an SEO content strategist. Research tools are DISABLED — you have only save_topic available.

TASK: Call save_topic exactly {needed} more times. Use the strategy context below to generate distinct, high-quality blog topics. Do NOT write a summary — call save_topic immediately.

Blog niche: {niche}
Target audience: {audience}

── YOUR PRODUCT ────────────────────────────────────────────────────────────────
{product_summary}

── STRATEGY CONTEXT ────────────────────────────────────────────────────────────
{strategy_context}

── CONTENT GAPS TO FILL ────────────────────────────────────────────────────────
{gaps_and_wins}

── PILLAR NAMES (use exact spelling) ───────────────────────────────────────────
{pillar_names}

── PILLAR COVERAGE (avoid duplicating covered angles) ──────────────────────────
{pillar_coverage_context}

Rules:
- Each topic must use a different keyword and belong to a different pillar where possible
- Pick content_angle values NOT already covered for that pillar (see coverage above)
- Include a detailed research_brief: angle/hook, 4-6 subtopics, reader pain point, suggested word count
- Each topic must connect to the product's use cases
- If a save_topic call is rejected as duplicate, immediately try a different keyword/angle

Valid content_angle values: {angles}"""


class ResearchAgent(BaseAgent):
    def __init__(self, client, model=None, provider=None):
        super().__init__(client, model, provider)
        self._topics_saved = 0
        self._topics_skipped = 0

    def run_research(self) -> int:
        strategy = get_active_strategy()
        strategy_context = _format_strategy(strategy)
        pillar_coverage = get_pillar_coverage()
        pillar_coverage_context = _format_pillar_coverage(pillar_coverage, strategy)
        product_summary = (strategy or {}).get("product_summary", "") or (
            f"Product URL: {config.PRODUCT_URL}" if config.PRODUCT_URL else
            "No product summary available — search broadly within the niche."
        )
        unreachable_context = _format_unreachable_competitors()

        system = SYSTEM.format(
            min_topics=config.MIN_TOPICS_PER_RESEARCH,
            niche=config.BLOG_NICHE or "general topics",
            audience=config.TARGET_AUDIENCE,
            product_summary=product_summary,
            strategy_context=strategy_context,
            pillar_coverage_context=pillar_coverage_context,
            unreachable_context=unreachable_context,
        )
        prompt = (
            f"Research and find 3-5 high-potential blog topics for a '{config.BLOG_NICHE or 'general'}' blog. "
            f"Each topic must be relevant to the product described above. "
            f"Check competitors for new posts, use keyword discovery for un-indexed topics, "
            f"and validate competition level before saving each topic. "
            f"Assign each topic to its pillar and pick an angle not yet covered for that pillar. "
            f"Include in each research_brief how the topic connects to the product's features or use cases. "
            f"You MUST call save_topic at least {config.MIN_TOPICS_PER_RESEARCH} times — do not finish without saving topics."
        )
        self.run(prompt, system, TOOLS, max_iterations=15)

        if self._topics_saved < config.MIN_TOPICS_PER_RESEARCH:
            self._run_save_only_pass(strategy, strategy_context, pillar_coverage_context, product_summary)

        return self._topics_saved

    def _run_save_only_pass(self, strategy, strategy_context, pillar_coverage_context, product_summary):
        needed = config.MIN_TOPICS_PER_RESEARCH - self._topics_saved
        gaps_and_wins = _format_gaps_and_wins(strategy)

        save_only_system = SAVE_ONLY_SYSTEM.format(
            needed=needed,
            niche=config.BLOG_NICHE or "general topics",
            audience=config.TARGET_AUDIENCE,
            product_summary=product_summary,
            strategy_context=strategy_context,
            gaps_and_wins=gaps_and_wins,
            pillar_names=_format_pillar_names(strategy),
            pillar_coverage_context=pillar_coverage_context,
            angles=", ".join(CONTENT_ANGLES),
        )
        prompt = (
            f"You must call save_topic {needed} more time(s) right now. "
            f"Use the strategy pillars, content gaps, and quick wins in your system prompt. "
            f"Each topic needs a unique keyword and pillar assignment. Call save_topic now — do not write a summary."
        )
        self.run(prompt, save_only_system, SAVE_ONLY_TOOLS, max_iterations=10)

    def _execute_tool(self, name: str, inputs: dict):
        if name == "web_search":
            return web_search(inputs["query"], inputs.get("max_results", 8))
        elif name == "get_gsc_queries":
            return get_top_queries(inputs.get("days", 28))
        elif name == "get_gsc_rising":
            return get_rising_queries(inputs.get("days", 14))
        elif name == "get_ga4_top_pages":
            return get_top_pages(inputs.get("days", 28), inputs.get("limit", 15))
        elif name == "get_ga4_declining":
            return get_declining_pages(inputs.get("days", 28))
        elif name == "check_competitor_new_posts":
            site_url = inputs["site_url"]
            unreachable = {r["competitor_url"] for r in get_unreachable_competitors()}
            if site_url in unreachable:
                return {
                    "skipped": True,
                    "reason": "Sitemap has failed 3+ consecutive times — skipping to save tool budget",
                }
            posts = get_sitemap_posts(site_url, inputs.get("days_recent", 14))
            if posts and "error" in posts[0]:
                record_sitemap_check(site_url, "error", posts[0]["error"])
                return posts
            record_sitemap_check(site_url, "ok")
            if not posts:
                return {"new_posts": [], "total_recent": 0, "new_count": 0}
            new = save_competitor_posts(site_url, posts)
            return {"new_posts": new, "total_recent": len(posts), "new_count": len(new)}
        elif name == "analyze_post":
            return fetch_post_summary(inputs["url"])
        elif name == "analyze_serp":
            return analyze_serp(inputs["keyword"], inputs.get("max_results", 8))
        elif name == "discover_keywords":
            return discover_keywords(inputs["seed_keyword"], inputs.get("max_patterns", 5))
        elif name == "get_google_trends":
            return get_google_trends(inputs["topic"])
        elif name == "save_topic":
            from dedup import DedupChecker
            is_dup, reason, match = DedupChecker().check(inputs["title"], inputs["keyword"])
            if is_dup:
                self._topics_skipped += 1
                return {
                    "skipped": True,
                    "reason": f"Duplicate detected: {reason}",
                    "nearest_match": match.get("title") if match else None,
                }
            topic_id = save_topic(
                title=inputs["title"],
                keyword=inputs["keyword"],
                research_brief=inputs["research_brief"],
                source=inputs.get("source", "web_search"),
                priority_score=inputs.get("priority_score", 0.5),
                pillar_name=inputs.get("pillar_name"),
                content_angle=inputs.get("content_angle"),
            )
            self._topics_saved += 1
            return {"success": True, "topic_id": topic_id, "saved": inputs["title"]}
        return {"error": f"Unknown tool: {name}"}


def _format_unreachable_competitors() -> str:
    rows = get_unreachable_competitors()
    if not rows:
        return "None — all competitor sitemaps are accessible."
    lines = []
    for r in rows:
        err = f" ({r['last_error']})" if r.get("last_error") else ""
        lines.append(f"  - {r['competitor_url']}{err}  [{r['consecutive_failures']} consecutive failures]")
    return "\n".join(lines)


def _format_pillar_names(strategy) -> str:
    if not strategy:
        return "(no strategy defined)"
    pillars = strategy.get("content_pillars", [])
    if not pillars:
        return "(no pillars defined)"
    return "\n".join(f"  - {p['name']}" for p in pillars)


def _format_gaps_and_wins(strategy) -> str:
    if not strategy:
        return "(no strategy defined)"
    lines = []
    gaps = strategy.get("content_gaps", [])
    wins = strategy.get("quick_wins", [])
    if gaps:
        lines.append(f"Content gaps: {', '.join(gaps[:8])}")
    if wins:
        lines.append(f"Quick win keywords: {', '.join(wins[:8])}")
    return "\n".join(lines) or "(none listed)"


def _format_pillar_coverage(coverage: dict, strategy: dict | None) -> str:
    """Format per-pillar angle coverage for injection into the system prompt."""
    all_pillars = []
    if strategy:
        all_pillars = [p["name"] for p in strategy.get("content_pillars", [])]

    if not all_pillars and not coverage:
        return "No strategy pillars defined yet."

    lines = []
    seen = set()
    for pillar in all_pillars:
        seen.add(pillar)
        covered = coverage.get(pillar, [])
        remaining = [a for a in CONTENT_ANGLES if a not in covered]
        if covered:
            lines.append(f"  {pillar}:")
            lines.append(f"    covered: {', '.join(covered)}")
            lines.append(f"    open angles: {', '.join(remaining) if remaining else 'all covered — pick least-used angle'}")
        else:
            lines.append(f"  {pillar}: (no posts yet — all angles open)")

    for pillar, covered in coverage.items():
        if pillar not in seen:
            remaining = [a for a in CONTENT_ANGLES if a not in covered]
            lines.append(f"  {pillar}: covered: {', '.join(covered)} | open: {', '.join(remaining)}")

    return "\n".join(lines) if lines else "No posts published or queued yet — all angles open for all pillars."


def _format_strategy(strategy: dict | None) -> str:
    if not strategy:
        return "No strategy set yet. Run: python main.py strategy\nProceeding with general research."

    pillars = strategy.get("content_pillars", [])
    competitors = strategy.get("competitors", [])
    quick_wins = strategy.get("quick_wins", [])
    gaps = strategy.get("content_gaps", [])

    lines = []
    if pillars:
        lines.append("Content pillars:")
        for p in pillars:
            kws = ", ".join(p.get("target_keywords", [])[:4])
            lines.append(f"  - {p['name']}: {kws}")
    if competitors:
        lines.append("\nCompetitors to monitor:")
        for c in competitors:
            lines.append(f"  - {c.get('url', '')} ({c.get('focus', '')})")
    if quick_wins:
        lines.append(f"\nQuick win keywords: {', '.join(quick_wins[:6])}")
    if gaps:
        lines.append(f"\nContent gaps to fill: {', '.join(gaps[:5])}")
    if strategy.get("strategic_summary"):
        lines.append(f"\nStrategy: {strategy['strategic_summary']}")

    return "\n".join(lines)
