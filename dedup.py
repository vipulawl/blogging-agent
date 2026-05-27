import re
import config
from storage.db import get_all_post_memory, get_all_topics

_STOPWORDS = {"the", "and", "for", "are", "was", "that", "with", "this", "from",
              "you", "your", "how", "what", "why", "when", "which", "will",
              "can", "not", "but", "all", "has", "have", "been", "more", "its"}


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z]+", text.lower())
    return {w for w in words if len(w) >= 3 and w not in _STOPWORDS}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _all_dedup_items() -> list[dict]:
    """Published posts + non-rejected pipeline topics — both compared as title+keyword."""
    items = []
    for p in get_all_post_memory():
        items.append({"title": p.get("title", ""), "keyword": p.get("keyword", ""), "source": "published"})
    for t in get_all_topics():
        if t.get("status") not in ("rejected",):
            items.append({"title": t.get("title", ""), "keyword": t.get("keyword", ""), "source": "queued"})
    return items


class DedupChecker:
    def __init__(self):
        self.threshold = config.DEDUP_THRESHOLD

    def check(self, title: str, keyword: str) -> tuple[bool, str, dict | None]:
        """
        Returns (is_duplicate, reason, nearest_match).
        Compares title+keyword of new topic against title+keyword of all existing
        published and in-pipeline topics (apples-to-apples).
        """
        query_tokens = _tokenize(f"{title} {keyword}")
        best_score = 0.0
        best_match = None

        for item in _all_dedup_items():
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
        if best_score >= self.threshold * 0.75:
            return (
                False,
                f"Near-duplicate (similarity {best_score:.2f}) vs '{best_match['title'] if best_match else 'none'}' — proceed with caution",
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
