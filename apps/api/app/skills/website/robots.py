from bs4 import BeautifulSoup


def check_robots(soup: BeautifulSoup) -> dict:
    tag = soup.find("meta", attrs={"name": "robots"})
    content = (tag.get("content", "") if tag else "").lower()

    finding: dict = {
        "present": bool(tag),
        "content": content or None,
    }

    if "noindex" in content:
        finding["severity"] = "high"
        finding["message"] = (
            "Page declares `noindex` — search engines and AI search engines will skip it."
        )
    elif "nofollow" in content:
        finding["severity"] = "medium"
        finding["message"] = (
            "Page declares `nofollow`. Outbound link equity will not pass through."
        )
    else:
        finding["severity"] = "ok"
        finding["message"] = "No restrictive robots directives."

    return finding
