import re
import config
from storage.db import get_all_post_memory, get_all_topics

_STOPWORDS = {"the", "and", "for", "are", "was", "that", "with", "this", "from",
              "you", "your", "how", "what", "why", "when", "which", "will",
              "can", "not", "but", "all", "has", "have", "been", "more", "its"}


def _normalize_keyword(kw: str) -> str:
    return re.sub(r"\s+", " ", kw.lower().strip())


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z]+", text.lower())
    return {w for w in words if len(w) >= 3 and w not in _STOPWORDS}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _all_dedup_items(exclude_topic_id: int = None) -> list[dict]:
    """Published posts + non-rejected pipeline topics."""
    items = []
    for p in get_all_post_memory():
        items.append({
            "title": p.get("title", ""),
            "keyword": p.get("keyword", ""),
            "pillar_name": p.get("pillar_name") or "",
            "content_angle": p.get("content_angle") or "",
            "source": "published",
        })
    for t in get_all_topics():
        if t.get("status") in ("rejected",):
            continue
        if exclude_topic_id and t.get("id") == exclude_topic_id:
            continue
        items.append({
            "title": t.get("title", ""),
            "keyword": t.get("keyword", ""),
            "pillar_name": t.get("pillar_name") or "",
            "content_angle": t.get("content_angle") or "",
            "source": t.get("status", "queued"),
        })
    return items


class DedupChecker:
    def __init__(self):
        self.threshold = config.DEDUP_THRESHOLD

    def check(self, title: str, keyword: str,
              pillar_name: str = None, content_angle: str = None,
              exclude_topic_id: int = None) -> tuple[bool, str, dict | None]:
        """
        Returns (is_duplicate, reason, nearest_match).
        Three ordered checks:
        1. Exact normalized keyword match against published + queued topics
        2. Duplicate pillar_name + content_angle when both are set
        3. Jaccard similarity >= threshold on title + keyword
        """
        items = _all_dedup_items(exclude_topic_id=exclude_topic_id)
        norm_kw = _normalize_keyword(keyword)

        # Check 1: exact normalized keyword match
        for item in items:
            if _normalize_keyword(item["keyword"]) == norm_kw:
                return (
                    True,
                    f"Exact keyword match '{keyword}' vs '{item['title']}' ({item['source']})",
                    item,
                )

        # Check 2: duplicate pillar_name + content_angle
        if pillar_name and content_angle:
            for item in items:
                if (item["pillar_name"] and item["content_angle"] and
                        item["pillar_name"].lower() == pillar_name.lower() and
                        item["content_angle"].lower() == content_angle.lower()):
                    return (
                        True,
                        f"Duplicate pillar+angle '{pillar_name}' / '{content_angle}' already covered by '{item['title']}' ({item['source']})",
                        item,
                    )

        # Check 3: Jaccard similarity on title + keyword
        query_tokens = _tokenize(f"{title} {keyword}")
        best_score = 0.0
        best_match = None
        for item in items:
            item_tokens = _tokenize(f"{item['title']} {item['keyword']}")
            score = _jaccard(query_tokens, item_tokens)
            if score > best_score:
                best_score = score
                best_match = item

        if best_score >= self.threshold:
            return (
                True,
                f"Similarity {best_score:.2f} >= threshold {self.threshold} vs '{best_match['title']}' ({best_match['source']})",
                best_match,
            )
        return (False, f"No duplicate found (max similarity {best_score:.2f})", None)

    def score_penalty(self, title: str, keyword: str) -> float:
        """Returns a dedup penalty (0.0–0.3) to subtract from scheduler score."""
        _, _, match = self.check(title, keyword)
        if match:
            query_tokens = _tokenize(f"{title} {keyword}")
            post_tokens = _tokenize(f"{match.get('title', '')} {match.get('keyword', '')}")
            score = _jaccard(query_tokens, post_tokens)
            return min(score * 0.4, 0.3)
        return 0.0
