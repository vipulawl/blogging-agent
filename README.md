# Blogging Agent

An AI-powered multi-agent pipeline that researches topics, writes blog posts, edits them, and queues them for your approval — outputting platform-agnostic markdown files.

## How it works

```
Research Agent → Writer Agent → Editor Agent → Your Approval → output/*.md
```

1. **Research Agent** pulls from Google Search Console, GA4, and DuckDuckGo to find high-potential topics
2. **Writer Agent** writes a full SEO-optimized article based on the research brief
3. **Editor Agent** reviews and substantially improves the draft
4. **You** review in the terminal and approve/reject
5. Approved posts are saved as `output/YYYY-MM-DD-slug.md` with YAML frontmatter — drop them into any static site

## Setup

### 1. Clone and install

```bash
git clone <your-repo>
cd blogging-agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your values (see below).

### 3. Configure Google APIs (optional but recommended)

Skip this if you only want DuckDuckGo-based research.

**Create a service account:**
1. Go to [Google Cloud Console](https://console.cloud.google.com) → New project
2. Enable: **Search Console API** and **Google Analytics Data API**
3. IAM & Admin → Service Accounts → Create service account
4. Create a JSON key and save it as `google-credentials.json` in the project root

**Grant access:**
- **GSC**: Go to [Search Console](https://search.google.com/search-console) → Settings → Users and permissions → Add your service account email as a viewer
- **GA4**: Go to GA4 → Admin → Account Access Management → Add your service account email as a viewer

**Set in `.env`:**
```
GOOGLE_CREDENTIALS_FILE=google-credentials.json
GSC_SITE_URL=https://yoursite.com/
GA4_PROPERTY_ID=123456789
```

## Usage

```bash
# Research new topics (saves to queue)
python main.py research

# Write + edit the top queued topic
python main.py write

# Write a specific topic by ID
python main.py write --topic-id 3

# Review and approve/reject pending articles
python main.py review

# Full pipeline: research (if queue empty) → write → review
python main.py pipeline

# List all topics in queue
python main.py list-topics

# List drafts awaiting approval
python main.py list-drafts
```

## Output format

Approved articles are saved to `output/YYYY-MM-DD-slug.md`:

```yaml
---
title: "Your Article Title"
date: "2026-05-21"
slug: "your-article-slug"
description: "SEO meta description"
tags: ["tag1", "tag2"]
status: published
---

Article content in markdown...
```

This frontmatter works with: **Vercel/Next.js**, **Astro**, **Hugo**, **Jekyll**, **Gatsby**, **Ghost** (via import), and any other markdown-based CMS.

## Configuration reference

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key |
| `BLOG_NICHE` | Yes | e.g. "SaaS marketing", "personal finance" |
| `TARGET_AUDIENCE` | Yes | e.g. "early-stage startup founders" |
| `BLOG_TONE` | No | Default: "informative and engaging" |
| `BLOG_LANGUAGE` | No | Default: "English" |
| `MODEL` | No | Default: claude-sonnet-4-6 |
| `GOOGLE_CREDENTIALS_FILE` | No | Path to service account JSON |
| `GSC_SITE_URL` | No | e.g. `https://yoursite.com/` |
| `GA4_PROPERTY_ID` | No | Numeric property ID from GA4 |
| `OUTPUT_DIR` | No | Default: `output` |

## API costs

Each full pipeline run (research + write + edit) uses approximately:
- ~50K–80K input tokens (with prompt caching, ~10K uncached)
- ~4K–8K output tokens
- Estimated: **$0.15–$0.40 per article** with claude-sonnet-4-6

## File structure

```
blogging-agent/
├── main.py              # CLI entry point
├── orchestrator.py      # Pipeline coordination + approval gate
├── config.py            # Environment config
├── agents/
│   ├── base.py          # Agentic loop base class
│   ├── research.py      # Research agent
│   ├── writer.py        # Writer agent
│   └── editor.py        # Editor agent
├── tools/
│   ├── search.py        # DuckDuckGo search
│   ├── gsc.py           # Google Search Console
│   └── ga4.py           # Google Analytics 4
├── storage/
│   └── db.py            # SQLite storage
├── output/              # Approved markdown articles
└── blogging_agent.db    # SQLite database (auto-created)
```
