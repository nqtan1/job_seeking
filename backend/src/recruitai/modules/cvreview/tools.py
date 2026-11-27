"""The CV review tool of the career pack (ADR 0039): the account's latest stored review. It never
starts one (a review takes minutes and would hold a worker); the CV Review page does."""

from recruitai.core.errors import NotFound
from recruitai.core.tools import Call, Tool, register
from recruitai.modules.cvreview import service as cvreview


async def _cv_review_latest(c: Call) -> dict[str, str]:
    rows = await cvreview.list_reviews(c.db, org_id=c.org_id, limit=1, offset=0)
    if not rows:
        raise NotFound("No CV review yet.")
    data = rows[0].data
    improve = {
        x["block_id"]: x["improve"] for x in data["comments"] if x.get("improve")
    }
    fixes = [improve[b] for b in data["summary"]["top_fixes"] if b in improve]
    return {
        "score": str(rows[0].score),
        "top_fixes": "\n".join(f"- {x}" for x in fixes),
    }


register(
    Tool(
        "cv_review_latest",
        "career",
        (("start", False),),
        ("score", "top_fixes"),
        page="/cv-review",
        flag="cv_review_enabled",
        mcp=True,
    ),
    _cv_review_latest,
)
