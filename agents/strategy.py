import json
from .base import BaseAgent
from tools.search import web_search
from tools.serp import analyze_serp, find_competitors_for_niche
from tools.competitors import get_sitemap_posts, fetch_post_summary
from tools.keyword_discovery import discover_keywords, get_google_trends
from tools.product_crawler import crawl_product_site
from storage.db import save_strategy

TOOLS = [
    {
        "name": "crawl_own_site",
        "description": (
            "Crawl your own product/service website to understand what you sell before doing any competitor research. "
            "Fetches the homepage plus key internal pages (features, pricing, about, use-cases, solutions). "
            "Call this FIRST — before any other tool — so all subsequent searches are grounded in what the product actually does."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The product website URL (e.g. https://yourproduct.com)"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "web_search",
        "description": "Search the web for niche context, competitor background, or industry insights.",
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
        "name": "find_serp_competitors",
        "description": "Search DuckDuckGo for niche-related queries and find which domains appear most often. These are your real SEO competitors.",
        "input_schema": {
            "type": "object",
            "properties": {
                "niche": {"type": "string", "description": "The blog niche (e.g. 'B2B SaaS marketing')"},
                "num_queries": {"type": "integer", "default": 5},
            },
            "required": ["niche"],
        },
    },
    {
        "name": "analyze_serp",
        "description": "Check who ranks top-10 for a specific keyword. Use to map the competitive landscape for key pillar topics.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string"},
                "max_results": {"type": "integer", "default": 10},
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "get_competitor_posts",
        "description": "Fetch a competitor's sitemap to see their recent content. Reveals topic focus and publishing cadence.",
        "input_schema": {
            "type": "object",
            "properties": {
                "site_url": {"type": "string", "description": "Competitor's base URL, e.g. https://example.com"},
                "days_recent": {"type": "integer", "default": 45},
            },
            "required": ["site_url"],
        },
    },
    {
        "name": "analyze_post",
        "description": "Fetch one competitor post and extract: title, H2 structure, word count. Use to understand content depth and structure.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "discover_keywords",
        "description": "Expand a seed keyword using intent-based search patterns (how to X, best X, X guide, etc.) via DuckDuckGo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "seed_keyword": {"type": "string"},
                "max_patterns": {"type": "integer", "default": 6},
            },
            "required": ["seed_keyword"],
        },
    },
    {
        "name": "get_google_trends",
        "description": "Fetch rising and top related queries for a topic via Google Trends. Good for spotting emerging keyword opportunities.",
        "input_schema": {
            "type": "object",
            "properties": {"topic": {"type": "string"}},
            "required": ["topic"],
        },
    },
    {
        "name": "save_strategy",
        "description": "Save the finalized content strategy. Call this LAST, after all research is complete.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content_pillars": {
                    "type": "array",
                    "description": "4-6 pillar topic clusters. Each has name, description, and 5-8 target keywords.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "target_keywords": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
                "competitors": {
                    "type": "array",
                    "description": "5-8 competitor sites to monitor.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "name": {"type": "string"},
                            "focus": {"type": "string", "description": "What they mostly write about"},
                            "why_relevant": {"type": "string"},
                        },
                    },
                },
                "content_gaps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Topics competitors rank for that this blog doesn't cover yet.",
                },
                "quick_wins": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Low-competition keywords or topics to go after first.",
                },
                "avoid_topics": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "strategic_summary": {
                    "type": "string",
                    "description": "2-3 sentence strategic rationale: why these pillars, why these competitors, what the content angle should be.",
                },
                "product_summary": {
                    "type": "string",
                    "description": (
                        "Concise summary of the product based on the website crawl. Include: what the product does "
                        "(one sentence), who it's for, the 3-5 key features or capabilities, the main problems it "
                        "solves, and what makes it different from competitors. This is injected into every future "
                        "research run, so be specific and use the product's own language."
                    ),
                },
            },
            "required": ["content_pillars", "competitors", "content_gaps", "quick_wins", "strategic_summary", "product_summary"],
        },
    },
]

SYSTEM = """You are a senior content strategist building a 6-month blogging strategy from scratch.

You have the following context from the blog owner:

{interview_context}

── STEP 0 (MANDATORY — do this before anything else) ──────────────────────────
Call crawl_own_site with the product URL provided above.

Read the result carefully. It tells you:
- What the product actually does (not just the niche label)
- Who the real target customer is
- What features/capabilities the product has
- What problems it solves
- The language and tone the company uses

Everything after this step must be grounded in what you learned about the product.
Do NOT use generic niche-label searches like "{niche} blog" or "{niche} tips".
Use product-specific searches like "tools that do X for Y audience" or "alternatives to [product category]".

── RESEARCH PROCESS ───────────────────────────────────────────────────────────
1. crawl_own_site — understand the product first (step 0 above)
2. find_serp_competitors — use product-specific queries derived from what you learned:
   - "[product category] software for [target customer]"
   - "[main problem it solves] tool"
   - "alternatives to [product name or category]"
   - "[key feature] platform for [use case]"
   NOT generic: "[niche] blog", "[niche] tips"
3. For the top 3-4 competitors found, call get_competitor_posts to see what they're publishing
4. Analyze 1-2 posts from each competitor to understand their content angle and depth
5. Call analyze_serp for 3-5 keywords directly tied to the product's use cases
6. Call discover_keywords for 2-3 seed keywords derived from the product's features/problems it solves
7. Call get_google_trends on 1-2 topics that connect the product's value to rising queries
8. Synthesize everything and save_strategy — include a product_summary that precisely describes
   what you learned about the product from the crawl

── STRATEGY QUALITY BAR ───────────────────────────────────────────────────────
- Content pillars must connect to the product's use cases, not just be generic niche topics
  GOOD: "Reducing SaaS churn in the first 30 days" (if the product helps with onboarding)
  BAD:  "SaaS growth tips"
- Each pillar needs real keywords with clear search intent tied to buyer problems the product solves
- Competitors must be actual SEO competitors (rank for same terms your potential customers search), not just popular blogs
- Content gaps = topics competitors rank for top 3 that your site doesn't have ANY content on
- Quick wins = keywords with likely low competition that are directly relevant to the product's features or use cases
- product_summary in save_strategy must be specific enough that a writer can reference it

Think like someone who has to achieve results in 90 days, not build a 5-year brand."""


class StrategyAgent(BaseAgent):
    def build_strategy(self, interview: dict) -> None:
        import config as cfg

        context_lines = [
            f"- Blog niche: {interview['niche']}",
            f"- Primary goal: {interview['goal']}",
            f"- Target reader: {interview['target_reader']}",
            f"- Desired reader action: {interview['desired_action']}",
            f"- Publishing frequency: {interview['frequency']}",
        ]
        if interview.get("avoid"):
            context_lines.append(f"- Avoid: {interview['avoid']}")

        product_url = cfg.PRODUCT_URL or interview.get("product_url", "")
        if product_url:
            context_lines.append(f"- Product URL: {product_url}")

        interview_context = "\n".join(context_lines)
        system = SYSTEM.format(interview_context=interview_context)

        if product_url:
            prompt = (
                f"Build a complete blogging strategy for a '{interview['niche']}' blog. "
                f"Start by calling crawl_own_site with '{product_url}' to understand the product, "
                f"then research the competitive landscape using product-specific queries, "
                f"identify content pillars tied to the product's use cases, find content gaps, and save the strategy."
            )
        else:
            prompt = (
                f"Build a complete blogging strategy for a '{interview['niche']}' blog. "
                f"Research the competitive landscape, identify content pillars and keyword clusters, "
                f"find content gaps, and save the strategy."
            )
        self.run(prompt, system, TOOLS, max_iterations=25)

    def _execute_tool(self, name: str, inputs: dict):
        if name == "crawl_own_site":
            return crawl_product_site(inputs["url"])
        elif name == "web_search":
            return web_search(inputs["query"], inputs.get("max_results", 8))
        elif name == "find_serp_competitors":
            return find_competitors_for_niche(inputs["niche"], inputs.get("num_queries", 5))
        elif name == "analyze_serp":
            return analyze_serp(inputs["keyword"], inputs.get("max_results", 10))
        elif name == "get_competitor_posts":
            return get_sitemap_posts(inputs["site_url"], inputs.get("days_recent", 45))
        elif name == "analyze_post":
            return fetch_post_summary(inputs["url"])
        elif name == "discover_keywords":
            return discover_keywords(inputs["seed_keyword"], inputs.get("max_patterns", 6))
        elif name == "get_google_trends":
            return get_google_trends(inputs["topic"])
        elif name == "save_strategy":
            save_strategy(inputs)
            return {"success": True}
        return {"error": f"Unknown tool: {name}"}
