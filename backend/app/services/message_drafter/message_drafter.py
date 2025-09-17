import re
from typing import Dict, Iterable, List, MutableMapping, Optional

from .prompts import CLOSE_PARAGRAPH, CURIOSITY_PARAGRAPH, INTRO_PARAGRAPH


def draft_messages(
    profiles: Iterable[MutableMapping[str, str]],
    intro_override: Optional[str] = None,
) -> List[Dict[str, str]]:
    drafted: List[Dict[str, str]] = []
    intro_paragraph = intro_override or INTRO_PARAGRAPH

    for profile in profiles:
        title = profile.get("title", "")
        name = _extract_candidate_name(title) or "there"
        company = profile.get("company")

        greeting = f"Hi {name},"
        opener = (
            f"I came across your profile while researching opportunities at {company}"
            if company
            else "I came across your profile while researching opportunities"
        )

        paragraphs = [
            greeting,
            "",
            intro_paragraph,
            opener
            + " and would love to learn more about the engineering culture and how the team supports new hires.",
            CURIOSITY_PARAGRAPH,
            CLOSE_PARAGRAPH,
            "",
            "Thanks so much,",
            "Yazeed",
        ]
        message = "\n".join(paragraphs)

        enriched = dict(profile)
        enriched["message"] = message
        drafted.append(enriched)

    return drafted


def _extract_candidate_name(title: str) -> str:
    # get candidate name from the SERP title (e.g., 'Jane Doe - Senior Engineer')

    if not title:
        return ""
    candidate = title.split("-", 1)[0]
    candidate = re.split(r"\bat\b", candidate, flags=re.IGNORECASE)[0]
    candidate = re.sub(r"[|,/]", " ", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip()
    return candidate
