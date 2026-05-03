import re

from bs4 import BeautifulSoup

SENTENCE_TERMINATORS = re.compile(r"[.!?]+\s")


def check_copy_clarity(soup: BeautifulSoup) -> dict:
    """Compute a coarse readability score over the visible body text."""
    # Drop scripts/styles before extracting text
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()

    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    word_count = len(text.split())

    # Sentence segmentation
    sentences = [s.strip() for s in SENTENCE_TERMINATORS.split(text) if s.strip()]
    sentence_count = len(sentences) if sentences else 1
    avg_sentence_length = (word_count / sentence_count) if sentence_count else 0.0

    # Long-word density
    long_word_count = sum(1 for w in text.split() if len(w) >= 12)
    long_word_pct = (long_word_count / word_count) if word_count else 0.0

    # Score: short sentences win; long-word density penalizes
    if word_count < 80:
        score = 30
        severity = "medium"
        message = (
            f"Page has only {word_count} words of body copy. "
            "Light pages may not give visitors enough to act on."
        )
    else:
        sentence_factor = max(0.0, 1.0 - max(0, avg_sentence_length - 18) / 12.0)
        long_word_factor = max(0.0, 1.0 - long_word_pct * 4)
        score = int(max(0, min(100, 100 * 0.6 * sentence_factor + 100 * 0.4 * long_word_factor + 5)))
        if avg_sentence_length > 28:
            severity = "medium"
            message = (
                f"Average sentence length is {avg_sentence_length:.1f} words. "
                "Trim to 12–20 words for scannability."
            )
        elif long_word_pct > 0.15:
            severity = "low"
            message = (
                f"{long_word_pct * 100:.0f}% of words are long (≥12 chars). "
                "Replace jargon with simpler synonyms where possible."
            )
        else:
            severity = "ok"
            message = "Copy reads at a brisk pace with manageable sentence length."

    return {
        "word_count": word_count,
        "sentence_count": sentence_count,
        "avg_sentence_length": round(avg_sentence_length, 1),
        "long_word_pct": round(long_word_pct, 3),
        "score": score,
        "severity": severity,
        "message": message,
    }
