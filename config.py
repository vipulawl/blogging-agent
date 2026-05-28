import os
from dotenv import load_dotenv

load_dotenv()

# ── Provider ──────────────────────────────────────────────────────────────────
# Options: "openai" | "ollama" | "anthropic"
PROVIDER = os.getenv("PROVIDER", "openai")

# Ollama (local, OpenAI-compatible)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:70b")

# Anthropic (fallback)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# OpenAI — used for all agents. Strategy uses gpt-4o-mini; Research uses gpt-4o-mini.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Which provider/model to use for the Strategy Agent specifically
STRATEGY_PROVIDER = os.getenv("STRATEGY_PROVIDER", "openai")
STRATEGY_MODEL = os.getenv("STRATEGY_MODEL", OPENAI_MODEL)

# Research Agent — tool-heavy (web search, SERP, GSC, competitors). Default: gpt-4o-mini.
RESEARCH_PROVIDER = os.getenv("RESEARCH_PROVIDER", "openai")
RESEARCH_MODEL = os.getenv("RESEARCH_MODEL", os.getenv("OPENAI_RESEARCH_MODEL", "gpt-4o-mini"))

# Resolved model name based on provider
def _resolve_model():
    if PROVIDER == "openai":
        return OPENAI_MODEL
    if PROVIDER == "ollama":
        return OLLAMA_MODEL
    return ANTHROPIC_MODEL

MODEL = os.getenv("MODEL") or _resolve_model()

# ── Product / website ─────────────────────────────────────────────────────────
# URL of the product/service the blog promotes. Used by the Strategy Agent to
# crawl your own site before searching for competitors, so research is grounded
# in what you actually sell rather than the generic niche label.
PRODUCT_URL = os.getenv("PRODUCT_URL", "")

# ── Blog identity ─────────────────────────────────────────────────────────────
BLOG_NICHE = os.getenv("BLOG_NICHE", "")
TARGET_AUDIENCE = os.getenv("TARGET_AUDIENCE", "general readers")
BLOG_TONE = os.getenv("BLOG_TONE", "informative and engaging")
BLOG_LANGUAGE = os.getenv("BLOG_LANGUAGE", "English")

# ── Google APIs (optional) ────────────────────────────────────────────────────
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "")
GSC_SITE_URL = os.getenv("GSC_SITE_URL", "")
GA4_PROPERTY_ID = os.getenv("GA4_PROPERTY_ID", "")

# ── Publishing ────────────────────────────────────────────────────────────────
# "pr"  → create a git branch + GitHub PR (merge = publish, Vercel auto-deploys)
# "cli" → blocking terminal review prompt (original behaviour)
APPROVAL_MODE = os.getenv("APPROVAL_MODE", "pr")

# Path (relative to REPO_DIR) where markdown articles are written
# Match your framework: "posts/", "src/content/blog/", "content/posts/", etc.
CONTENT_DIR = os.getenv("CONTENT_DIR", "output")

# Absolute path to your site's git repo root (defaults to current working dir)
REPO_DIR = os.getenv("REPO_DIR", "")

# ── Daemon behaviour ──────────────────────────────────────────────────────────
# How often the daemon wakes up to check (minutes)
POLL_INTERVAL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", "60"))
# Trigger research when queued topics drop below this number
MIN_QUEUE_SIZE = int(os.getenv("MIN_QUEUE_SIZE", "3"))
# Minimum save_topic calls required for a research run to be considered successful
MIN_TOPICS_PER_RESEARCH = int(os.getenv("MIN_TOPICS_PER_RESEARCH", "3"))
# Max articles written per calendar day
MAX_ARTICLES_PER_DAY = int(os.getenv("MAX_ARTICLES_PER_DAY", "1"))

# ── Smart systems ────────────────────────────────────────────────────────────
# Jaccard similarity threshold above which a topic is considered a duplicate
DEDUP_THRESHOLD = float(os.getenv("DEDUP_THRESHOLD", "0.80"))
# Days after publication before a post is eligible for performance flagging
PERFORMANCE_CHECK_DAYS = int(os.getenv("PERFORMANCE_CHECK_DAYS", "30"))
# Set to "true" in GitHub Actions to execute corrections without terminal prompts
CORRECTION_AUTO_MODE = os.getenv("CORRECTION_AUTO_MODE", "false")

# ── Legacy ───────────────────────────────────────────────────────────────────
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")
