from bs4 import BeautifulSoup, Tag

CLEAR_CTA_PHRASES = (
    "get started",
    "start free",
    "start your free",
    "try it free",
    "try for free",
    "try free",
    "book a demo",
    "book demo",
    "request a demo",
    "schedule a demo",
    "sign up",
    "create account",
    "get a quote",
    "buy now",
    "add to cart",
    "subscribe",
    "join now",
    "join the",
    "claim your",
    "talk to sales",
)

VAGUE_CTA_PHRASES = (
    "learn more",
    "click here",
    "read more",
    "find out",
    "explore",
    "see more",
    "discover",
    "submit",
    "go",
    "ok",
)


def _cta_text(tag: Tag) -> str:
    text = tag.get_text(" ", strip=True)
    return " ".join(text.split())[:120]


def check_cta_analysis(soup: BeautifulSoup) -> dict:
    """Find primary CTAs and score their clarity."""
    candidates: list[Tag] = []

    # Buttons
    candidates.extend(soup.find_all("button"))

    # Anchors that look like buttons (class contains btn / cta) or that have role="button"
    for a in soup.find_all("a"):
        cls = " ".join(a.get("class", [])).lower()
        role = (a.get("role") or "").lower()
        if "btn" in cls or "button" in cls or "cta" in cls or role == "button":
            candidates.append(a)

    # `<input type=submit|button>`
    for inp in soup.find_all("input", attrs={"type": ["submit", "button"]}):
        candidates.append(inp)

    cta_texts: list[str] = []
    for tag in candidates:
        text = _cta_text(tag) if not (tag.name == "input") else (tag.get("value") or "").strip()
        if not text:
            continue
        cta_texts.append(text)

    cta_count = len(cta_texts)

    clear_count = 0
    vague_count = 0
    primary_cta_text: str | None = None
    primary_clarity: str | None = None

    for text in cta_texts:
        lowered = text.lower()
        if primary_cta_text is None:
            primary_cta_text = text
        is_clear = any(phrase in lowered for phrase in CLEAR_CTA_PHRASES)
        is_vague = any(lowered == phrase or lowered.startswith(phrase) for phrase in VAGUE_CTA_PHRASES)
        if is_clear:
            clear_count += 1
            if primary_cta_text == text:
                primary_clarity = "clear"
        elif is_vague:
            vague_count += 1
            if primary_cta_text == text:
                primary_clarity = "vague"
        else:
            if primary_cta_text == text and primary_clarity is None:
                primary_clarity = "ambiguous"

    if cta_count == 0:
        score = 0
        severity = "high"
        message = "No CTA buttons or button-like links found above the fold."
    else:
        # Reward clear CTAs, penalize vague ones, normalize by total
        clear_pct = clear_count / cta_count
        vague_pct = vague_count / cta_count
        score = max(0, min(100, int((clear_pct * 100) - (vague_pct * 60) + 30)))
        if primary_clarity == "clear":
            severity = "ok" if vague_pct < 0.3 else "low"
            message = (
                f"Primary CTA looks clear ('{primary_cta_text}'). "
                f"{clear_count}/{cta_count} CTAs use action-led copy."
            )
        elif primary_clarity == "vague":
            severity = "medium"
            message = (
                f"Primary CTA copy is vague ('{primary_cta_text}'). "
                "Action-led copy ('Get started', 'Book a demo') typically lifts CTR."
            )
        else:
            severity = "low"
            message = (
                f"Primary CTA copy is ambiguous ('{primary_cta_text}'). "
                "Consider tightening to a clear next step."
            )

    return {
        "cta_count": cta_count,
        "primary_cta_text": primary_cta_text,
        "primary_clarity": primary_clarity,
        "clear_count": clear_count,
        "vague_count": vague_count,
        "score": score,
        "severity": severity,
        "message": message,
    }
