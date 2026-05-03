import re

from bs4 import BeautifulSoup

VALUE_WORDS = (
    "save",
    "grow",
    "increase",
    "reduce",
    "automate",
    "scale",
    "free",
    "fast",
    "instant",
    "for ",  # "for marketers", "for SaaS"
    "without",
    "no ",
    "stop ",
)


def check_above_fold(soup: BeautifulSoup) -> dict:
    h1_tag = soup.find("h1")
    h1_text = (h1_tag.get_text(" ", strip=True) if h1_tag else "").strip()

    first_paragraph = ""
    if h1_tag is not None:
        next_p = h1_tag.find_next("p")
        if next_p is not None:
            first_paragraph = next_p.get_text(" ", strip=True)
    if not first_paragraph:
        any_p = soup.find("p")
        if any_p is not None:
            first_paragraph = any_p.get_text(" ", strip=True)
    first_paragraph = first_paragraph[:600]

    has_h1 = bool(h1_text)
    h1_length = len(h1_text)
    paragraph_length = len(first_paragraph)
    benefit_signals = 0
    combined = f"{h1_text} {first_paragraph}".lower()
    for word in VALUE_WORDS:
        if word in combined:
            benefit_signals += 1
    has_number = bool(re.search(r"\d{2,}|\d+%|\$\d", combined))

    score = 0
    if has_h1:
        score += 30
        if 18 <= h1_length <= 90:
            score += 15
    if paragraph_length >= 60:
        score += 15
    score += min(20, benefit_signals * 5)
    if has_number:
        score += 10
    score = min(100, score)

    if not has_h1:
        severity = "high"
        message = "Missing H1 above the fold. Visitors can't tell what the page is about at a glance."
    elif h1_length < 18:
        severity = "medium"
        message = (
            f"H1 is very short ('{h1_text}'). Aim for a 5–12 word benefit-led headline."
        )
    elif paragraph_length < 40:
        severity = "medium"
        message = (
            "H1 is set, but the supporting paragraph below is missing or too short. "
            "Add a 1–2 sentence value prop."
        )
    elif benefit_signals == 0:
        severity = "low"
        message = (
            "Hero copy lacks benefit/value language (save / grow / automate / for / without). "
            "Consider sharpening the outcome promise."
        )
    else:
        severity = "ok"
        message = "Hero section communicates a clear, benefit-driven value prop."

    return {
        "h1_text": h1_text,
        "h1_length": h1_length,
        "first_paragraph": first_paragraph,
        "first_paragraph_length": paragraph_length,
        "benefit_signals": benefit_signals,
        "has_number_proof": has_number,
        "score": score,
        "severity": severity,
        "message": message,
    }
