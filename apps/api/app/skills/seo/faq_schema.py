import json

from bs4 import BeautifulSoup


def _has_type(payload: object, target: str) -> bool:
    if isinstance(payload, dict):
        types = payload.get("@type")
        if isinstance(types, str) and types == target:
            return True
        if isinstance(types, list) and target in types:
            return True
        if "@graph" in payload and isinstance(payload["@graph"], list):
            for item in payload["@graph"]:
                if _has_type(item, target):
                    return True
    elif isinstance(payload, list):
        return any(_has_type(item, target) for item in payload)
    return False


def check_faq_schema(soup: BeautifulSoup) -> dict:
    has_faq = False
    for block in soup.find_all("script", type="application/ld+json"):
        raw = (block.string or block.get_text() or "").strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if _has_type(payload, "FAQPage"):
            has_faq = True
            break

    finding: dict = {"present": has_faq}
    if has_faq:
        finding["severity"] = "ok"
        finding["message"] = "FAQ schema (`FAQPage`) is present — AI search engines can extract Q&A."
    else:
        finding["severity"] = "low"
        finding["message"] = (
            "No FAQ schema found. Adding `FAQPage` markup makes the page eligible for direct "
            "answer placements in Google and AI search engines."
        )
    return finding
