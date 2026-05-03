from bs4 import BeautifulSoup


def check_title(soup: BeautifulSoup) -> dict:
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None

    finding: dict = {
        "present": bool(title),
        "title": title,
        "length": len(title) if title else 0,
    }

    if not title:
        finding["severity"] = "high"
        finding["message"] = "No <title> tag found. This hurts both SEO and AI search visibility."
    elif len(title) < 25:
        finding["severity"] = "medium"
        finding["message"] = (
            f"Title is short ({len(title)} chars). Aim for 30–60 characters with a clear value prop."
        )
    elif len(title) > 65:
        finding["severity"] = "low"
        finding["message"] = (
            f"Title is long ({len(title)} chars) and may truncate in search results."
        )
    else:
        finding["severity"] = "ok"
        finding["message"] = "Title length is within the recommended 30–60 character range."

    return finding
