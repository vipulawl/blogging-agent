import config
from .base import BaseAgent
from tools.search import web_search
from tools.gsc import get_top_queries, get_rising_queries
from tools.ga4 import get_top_pages, get_declining_pages
from storage.db import save_topic

TOOLS = [
    {
        "name": "web_search",
        "description": "Search the web via DuckDuckGo. Use to find trending topics, competitor articles, and what questions people are asking in the niche.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "description": "Number of results (1–10)", "default": 8},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_gsc_queries",
        "description": "Get top search queries from Google Search Console with impressions, clicks, CTR, and position. High impressions + low CTR or position 5–20 = easy wins. Returns [] if GSC is not configured.",
        "input_schema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "description": "Lookback period in days", "default": 28}},
        },
    },
    {
        "name": "get_gsc_rising_queries",
        "description": "Get queries that are gaining impressions recently (rising trends). Returns [] if GSC is not configured.",
        "input_schema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "default": 14}},
        },
    },
    {
        "name": "get_ga4_top_pages",
        "description": "Get top performing pages from GA4 by sessions. Helps identify what content resonates — write more like these. Returns [] if GA4 is not configured.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 28},
                "limit": {"type": "integer", "default": 15},
            },
        },
    },
    {
        "name": "get_ga4_declining_pages",
        "description": "Get pages with falling traffic — candidates for refresh/update articles. Returns [] if GA4 is not configured.",
        "input_schema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "default": 28}},
        },
    },
    {
        "name": "save_topic",
        "description": "Save a topic to the writing queue.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Specific, SEO-friendly article title"},
                "keyword": {"type": "string", "description": "Primary keyword to target"},
                "research_brief": {
                    "type": "string",
                    "description": "Detailed brief for the writer: angle/hook, 4–6 subtopics to cover, target reader pain points, key insight from competitor research, suggested word count (800–2500)",
                },
                "source": {
                    "type": "string",
                    "description": "Primary data source: gsc, ga4, web_search",
                    "default": "web_search",
                },
                "priority_score": {
                    "type": "number",
                    "description": "Priority 0.0–1.0 (1 = highest). Base on search volume/opportunity size.",
                    "default": 0.5,
                },
            },
            "required": ["title", "keyword", "research_brief"],
        },
    },
]

SYSTEM = """You are an expert SEO research agent. Identify 3–5 high-potential blog topics by analysing all available data sources.

Blog niche: {niche}
Target audience: {audience}

Research strategy:
1. Call get_gsc_queries — find queries where impressions > 100 but CTR < 5%, or position between 5–20 (these are easy ranking wins)
2. Call get_gsc_rising_queries — spot emerging topics before they're competitive
3. Call get_ga4_top_pages — identify what content format and topic clusters already work
4. Call get_ga4_declining_pages — find articles that need a refresh (these often rank again after an update)
5. Do 2–3 web_search calls on the most promising angles you've found (competitor gap analysis, "people also ask" style queries)
6. Save 3–5 specific, actionable topics with rich research briefs

For each research_brief include:
- Unique angle or hook that differentiates from existing content
- 4–6 specific subtopics/sections to cover
- Key reader pain point this addresses
- One concrete insight from your web search (competitor gap, trending angle, or data point)
- Suggested word count

Prefer specific over generic: "How to reduce SaaS churn in the first 30 days" beats "SaaS churn guide"."""


class ResearchAgent(BaseAgent):
    def run_research(self) -> None:
        system = SYSTEM.format(
            niche=config.BLOG_NICHE or "general topics",
            audience=config.TARGET_AUDIENCE,
        )
        prompt = (
            f"Research and find 3–5 high-potential blog topics for a '{config.BLOG_NICHE or 'general'}' blog "
            f"targeting '{config.TARGET_AUDIENCE}'. Use all available data sources, then save each topic with a detailed brief."
        )
        self.run(prompt, system, TOOLS)

    def _execute_tool(self, name: str, inputs: dict):
        if name == "web_search":
            return web_search(inputs["query"], inputs.get("max_results", 8))
        elif name == "get_gsc_queries":
            return get_top_queries(inputs.get("days", 28))
        elif name == "get_gsc_rising_queries":
            return get_rising_queries(inputs.get("days", 14))
        elif name == "get_ga4_top_pages":
            return get_top_pages(inputs.get("days", 28), inputs.get("limit", 15))
        elif name == "get_ga4_declining_pages":
            return get_declining_pages(inputs.get("days", 28))
        elif name == "save_topic":
            topic_id = save_topic(
                title=inputs["title"],
                keyword=inputs["keyword"],
                research_brief=inputs["research_brief"],
                source=inputs.get("source", "web_search"),
                priority_score=inputs.get("priority_score", 0.5),
            )
            return {"success": True, "topic_id": topic_id, "saved": inputs["title"]}
        return {"error": f"Unknown tool: {name}"}
