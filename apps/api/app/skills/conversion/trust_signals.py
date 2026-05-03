import re

from bs4 import BeautifulSoup

TRUST_KEYWORDS = (
    "testimonial",
    "trusted by",
    "as seen on",
    "case study",
    "review",
    "rating",
    "g2",
    "capterra",
    "trustpilot",
    "soc 2",
    "iso 27001",
    "gdpr",
    "money-back",
    "money back guarantee",
    "satisfaction guarantee",
    "secure",
)

LOGO_HINT_CLASSES = ("logo-cloud", "customers-logos", "logo-grid", "client-logos")


def check_trust_signals(soup: BeautifulSoup) -> dict:
    text = soup.get_text(" ", strip=True).lower()
    hits: list[str] = []
    for keyword in TRUST_KEYWORDS:
        if keyword in text and keyword not in hits:
            hits.append(keyword)

    quotes = soup.find_all("blockquote")
    quote_count = len(quotes)

    # Detect customer logo cloud sections by class hints
    logo_section = False
    for cls_hint in LOGO_HINT_CLASSES:
        if soup.find(class_=re.compile(cls_hint, re.I)):
            logo_section = True
            break

    # Star ratings: spans/text with 4.7/5 or "★"
    rating_match = re.search(r"\b([4-5](?:\.[0-9])?)\s*/\s*5\b", text)
    star_rating = float(rating_match.group(1)) if rating_match else None

    has_stars = "★" in text or "★" in soup.decode()

    signal_count = (
        len(hits)
        + (1 if quote_count else 0)
        + (1 if logo_section else 0)
        + (1 if star_rating else 0)
        + (1 if has_stars else 0)
    )

    if signal_count == 0:
        severity = "high"
        message = (
            "No trust signals detected. Add customer logos, testimonials, ratings, "
            "or compliance badges above the fold."
        )
        score = 0
    elif signal_count == 1:
        severity = "medium"
        message = (
            "Only one trust signal detected. Stack 2–3 (logos + a quote + a rating) for stronger "
            "above-the-fold credibility."
        )
        score = 35
    elif signal_count == 2:
        severity = "low"
        message = "Trust signals present, but adding social proof above the fold compounds gains."
        score = 65
    else:
        severity = "ok"
        message = "Strong stack of trust signals."
        score = 90

    return {
        "keywords_found": hits,
        "quote_count": quote_count,
        "logo_section": logo_section,
        "star_rating": star_rating,
        "has_star_glyph": has_stars,
        "signal_count": signal_count,
        "score": score,
        "severity": severity,
        "message": message,
    }
