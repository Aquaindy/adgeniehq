from bs4 import BeautifulSoup


def check_viewport(soup: BeautifulSoup) -> dict:
    tag = soup.find("meta", attrs={"name": "viewport"})
    content = tag.get("content", "").strip() if tag else None

    finding: dict = {
        "present": bool(content),
        "content": content,
    }

    if not content:
        finding["severity"] = "high"
        finding["message"] = (
            "No mobile viewport meta tag. The page may render at desktop scale on phones."
        )
    elif "width=device-width" not in content.lower():
        finding["severity"] = "medium"
        finding["message"] = (
            "Viewport tag is set but does not include `width=device-width` — mobile rendering may break."
        )
    else:
        finding["severity"] = "ok"
        finding["message"] = "Mobile viewport is configured."

    return finding
