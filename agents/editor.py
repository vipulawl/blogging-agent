from .base import BaseAgent
from tools.search import web_search
from storage.db import save_edited_draft

TOOLS = [
    {
        "name": "web_search",
        "description": (
            "Search the web to fact-check specific statistics, dates, or claims in the draft. "
            "Use 1–2 targeted searches only — e.g. to verify a quoted percentage or a product release date."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "save_edited_draft",
        "description": "Save the edited article. Call this once your edits are complete.",
        "input_schema": {
            "type": "object",
            "properties": {
                "draft_id": {"type": "integer"},
                "content": {"type": "string", "description": "Full edited article in markdown"},
                "edit_notes": {
                    "type": "string",
                    "description": "Bullet-point summary of changes made and the reasoning behind each change",
                },
                "title": {"type": "string", "description": "Updated title if you improved it (optional)"},
                "meta_description": {"type": "string", "description": "Updated meta description if you improved it (optional)"},
            },
            "required": ["draft_id", "content", "edit_notes"],
        },
    },
]

SYSTEM = """You are an expert blog editor. Substantially improve the draft — not just typos.

Before editing, do these checks:
- Run 1–2 web_search calls to fact-check specific statistics or claims that seem approximate or dated.
  Correct anything wrong; add an inline note if you update a figure.
- Confirm the primary keyword appears in the opening paragraph. Weave it in naturally if missing.
- Confirm the primary keyword appears in at least one H2 heading. Adjust a heading if missing.
- Check that the draft covers all subtopics listed in the research brief. Add a concise paragraph
  for any missing or thin subtopic.

Then review and fix:
1. **Hook** — is the opening compelling? If not, rewrite the first paragraph.
2. **Structure** — does the article flow logically? Reorder sections if needed.
3. **Clarity** — simplify jargon, shorten long sentences, cut padding.
4. **Depth** — fill sections that are vague or generic with more specific language.
5. **SEO** — primary keyword should appear naturally in the opening, one H2, and conclusion. Not stuffed.
6. **Conclusion** — must be actionable. Remove "in conclusion" phrasing.
7. **Formatting** — fix any markdown issues, ensure headers are hierarchical.

Write edit_notes as a concise bullet list: what you changed and why."""


class EditorAgent(BaseAgent):
    def edit_article(self, draft: dict) -> None:
        self._topic_id = draft.get("topic_id")
        self._topic_title = draft.get("title")

        brief_section = ""
        if draft.get("research_brief"):
            brief_section = f"\n\n**Research brief (subtopics to cover):**\n{draft['research_brief']}"

        prompt = f"""Edit and improve this draft article (draft_id: {draft['id']}).

**Title:** {draft['title']}
**Primary keyword:** {draft['keyword']}
**Meta description:** {draft['meta_description']}{brief_section}

---

{draft['content']}

---

Start by running 1–2 web_search calls to fact-check claims, then verify keyword placement and brief coverage, then make all edits and save with save_edited_draft."""

        self.run(prompt, SYSTEM, TOOLS)

    def _execute_tool(self, name: str, inputs: dict):
        if name == "web_search":
            return web_search(inputs["query"], inputs.get("max_results", 5))
        if name == "save_edited_draft":
            save_edited_draft(
                draft_id=inputs["draft_id"],
                content=inputs["content"],
                edit_notes=inputs["edit_notes"],
                title=inputs.get("title"),
                meta_description=inputs.get("meta_description"),
            )
            return {
                "success": True,
                "word_count": len(inputs["content"].split()),
                "edit_notes": inputs["edit_notes"],
            }
        return {"error": f"Unknown tool: {name}"}
