from bs4 import BeautifulSoup

REQUIRED_PROPERTIES = ("og:title", "og:description", "og:url", "og:image")


def check_open_graph(soup: BeautifulSoup) -> dict:
    found: dict[str, str] = {}
    for tag in soup.find_all("meta"):
        prop = (tag.get("property") or "").strip()
        if prop.startswith("og:"):
            content = (tag.get("content") or "").strip()
            if content:
                found[prop] = content

    missing = [p for p in REQUIRED_PROPERTIES if p not in found]

    finding: dict = {
        "present_count": len(found),
        "found_properties": sorted(found.keys()),
        "missing_required": missing,
    }
    if not found:
        finding["severity"] = "medium"
        finding["message"] = (
            "No Open Graph tags. Social and AI-search snippets will fall back to <title>/meta only."
        )
    elif missing:
        finding["severity"] = "low"
        finding["message"] = (
            f"Missing Open Graph properties: {', '.join(missing)}."
        )
    else:
        finding["severity"] = "ok"
        finding["message"] = "All core Open Graph properties present."
    return finding
