import requests
from urllib.parse import urljoin, urlparse

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BlogResearchBot/1.0; +https://github.com)"}

# Nav link keywords that indicate an important product page worth crawling
_KEY_PAGE_SIGNALS = [
    "feature", "pricing", "price", "about", "how-it-work", "solution",
    "use-case", "usecase", "product", "service", "platform", "integration",
    "benefit", "why-us", "why-", "what-we", "overview", "tour",
]


def crawl_product_site(url: str) -> dict:
    """
    Crawl the product website and return a structured summary.

    Fetches the homepage then discovers and fetches up to 4 key internal pages
    (features, pricing, about, use-cases, etc.). Returns raw content for the
    strategy agent to interpret — what the product does, who it's for, key
    features, problems it solves, and tone.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return {"error": "beautifulsoup4 not installed — run: pip install beautifulsoup4"}

    base = url.rstrip("/")
    parsed = urlparse(base)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    def _get(page_url: str, timeout: int = 10):
        try:
            r = requests.get(page_url, timeout=timeout, headers=HEADERS)
            return r if r.status_code == 200 else None
        except Exception:
            return None

    def _clean_text(soup, max_words: int = 350) -> str:
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "svg"]):
            tag.decompose()
        raw = " ".join(soup.get_text(separator=" ").split())
        return " ".join(raw.split()[:max_words])

    def _headings(soup, tags=("h1", "h2", "h3"), limit: int = 12) -> list[str]:
        return [h.get_text(strip=True) for h in soup.find_all(tags)][:limit]

    def _discover_key_pages(soup) -> list[str]:
        seen, found = set(), []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            full = urljoin(origin, href)
            # internal only, no anchors/query strings/files
            if urlparse(full).netloc != parsed.netloc:
                continue
            if any(x in full for x in ["#", "?", ".pdf", ".png", ".jpg", ".svg", ".zip"]):
                continue
            path_lower = urlparse(full).path.lower()
            if full not in seen and any(sig in path_lower for sig in _KEY_PAGE_SIGNALS):
                seen.add(full)
                found.append(full)
        return found[:5]

    # ── Homepage ──────────────────────────────────────────────────────────────
    r = _get(base)
    if not r:
        return {"error": f"Could not fetch {url} (timeout or non-200 response)"}

    soup = BeautifulSoup(r.text, "html.parser")

    title_el   = soup.find("title")
    h1_el      = soup.find("h1")
    og_title   = soup.find("meta", {"property": "og:title"})
    meta_desc  = (soup.find("meta", {"name": "description"}) or
                  soup.find("meta", {"property": "og:description"}))

    raw_name = ""
    for el in [og_title, title_el]:
        if el:
            raw_name = el.get("content", "") or el.get_text(strip=True)
            if raw_name:
                break
    if not raw_name and h1_el:
        raw_name = h1_el.get_text(strip=True)
    # Strip common site-name suffixes: "Product | Tagline" → "Product"
    for sep in (" | ", " - ", " – ", " — "):
        if sep in raw_name:
            raw_name = raw_name.split(sep)[0].strip()
            break

    tagline = (meta_desc.get("content", "").strip() if meta_desc else "") or (h1_el.get_text(strip=True) if h1_el else "")

    homepage_data = {
        "url": base,
        "product_name": raw_name or parsed.netloc,
        "tagline": tagline,
        "headings": _headings(soup),
        "content_preview": _clean_text(soup),
    }

    # ── Key internal pages ────────────────────────────────────────────────────
    key_page_urls = _discover_key_pages(soup)
    key_pages = []
    for page_url in key_page_urls:
        pr = _get(page_url)
        if not pr:
            continue
        ps = BeautifulSoup(pr.text, "html.parser")
        h1 = ps.find("h1")
        key_pages.append({
            "url": page_url,
            "page_name": urlparse(page_url).path.strip("/").split("/")[-1],
            "h1": h1.get_text(strip=True) if h1 else "",
            "headings": _headings(ps, tags=("h2", "h3"), limit=10),
            "content_preview": _clean_text(ps, max_words=250),
        })

    return {
        "homepage": homepage_data,
        "key_pages": key_pages,
        "pages_crawled": 1 + len(key_pages),
    }
