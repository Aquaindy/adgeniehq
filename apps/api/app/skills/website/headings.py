from bs4 import BeautifulSoup


def check_headings(soup: BeautifulSoup) -> dict:
    h1_tags = soup.find_all("h1")
    h1_texts = [h.get_text(strip=True) for h in h1_tags if h.get_text(strip=True)]

    finding: dict = {
        "h1_count": len(h1_texts),
        "first_h1": h1_texts[0] if h1_texts else None,
    }

    if len(h1_texts) == 0:
        finding["severity"] = "high"
        finding["message"] = "No visible <h1> heading found. The above-the-fold message is unclear."
    elif len(h1_texts) > 1:
        finding["severity"] = "medium"
        finding["message"] = (
            f"Found {len(h1_texts)} <h1> tags. Use exactly one for hierarchy clarity."
        )
    else:
        first = h1_texts[0]
        if len(first) < 12:
            finding["severity"] = "medium"
            finding["message"] = (
                f"H1 is very short ('{first}'). Consider a benefit-driven hero headline."
            )
        else:
            finding["severity"] = "ok"
            finding["message"] = "Single, substantive <h1> detected."

    return finding
