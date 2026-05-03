from bs4 import BeautifulSoup


def check_canonical(soup: BeautifulSoup, *, page_url: str) -> dict:
    tag = soup.find("link", attrs={"rel": "canonical"})
    href = tag.get("href", "").strip() if tag else None

    finding: dict = {
        "present": bool(href),
        "canonical_url": href,
        "page_url": page_url,
    }
    if not href:
        finding["severity"] = "medium"
        finding["message"] = (
            "Missing canonical link. Search engines may pick the wrong canonical version."
        )
    elif href != page_url and not page_url.rstrip("/").startswith(href.rstrip("/")):
        finding["severity"] = "low"
        finding["message"] = (
            f"Canonical points to {href}, which differs from the fetched URL. "
            "Verify this is intentional."
        )
    else:
        finding["severity"] = "ok"
        finding["message"] = "Canonical link is set."
    return finding
