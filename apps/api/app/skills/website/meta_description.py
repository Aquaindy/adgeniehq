from bs4 import BeautifulSoup


def check_meta_description(soup: BeautifulSoup) -> dict:
    tag = soup.find("meta", attrs={"name": "description"})
    description = tag.get("content", "").strip() if tag else None

    finding: dict = {
        "present": bool(description),
        "description": description,
        "length": len(description) if description else 0,
    }

    if not description:
        finding["severity"] = "high"
        finding["message"] = (
            "Missing meta description. Add a 120–160 character summary with the offer + value prop."
        )
    elif len(description) < 80:
        finding["severity"] = "medium"
        finding["message"] = (
            f"Meta description is short ({len(description)} chars). Aim for 120–160 chars."
        )
    elif len(description) > 165:
        finding["severity"] = "low"
        finding["message"] = (
            f"Meta description is long ({len(description)} chars) and may truncate."
        )
    else:
        finding["severity"] = "ok"
        finding["message"] = "Meta description length is within the recommended range."

    return finding
