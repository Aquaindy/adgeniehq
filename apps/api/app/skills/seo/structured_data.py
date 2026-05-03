import json

from bs4 import BeautifulSoup


def _types_in(payload: object) -> list[str]:
    if isinstance(payload, dict):
        types: list[str] = []
        if "@type" in payload:
            t = payload["@type"]
            if isinstance(t, list):
                types.extend([str(x) for x in t])
            else:
                types.append(str(t))
        if "@graph" in payload and isinstance(payload["@graph"], list):
            for item in payload["@graph"]:
                types.extend(_types_in(item))
        return types
    if isinstance(payload, list):
        out: list[str] = []
        for item in payload:
            out.extend(_types_in(item))
        return out
    return []


def check_structured_data(soup: BeautifulSoup) -> dict:
    blocks = soup.find_all("script", type="application/ld+json")
    types: list[str] = []
    invalid_blocks = 0

    for block in blocks:
        raw = (block.string or block.get_text() or "").strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            invalid_blocks += 1
            continue
        types.extend(_types_in(payload))

    types_unique = sorted({t for t in types if t})

    finding: dict = {
        "block_count": len(blocks),
        "valid_block_count": len(blocks) - invalid_blocks,
        "invalid_block_count": invalid_blocks,
        "types": types_unique,
    }

    if len(blocks) == 0:
        finding["severity"] = "medium"
        finding["message"] = (
            "No JSON-LD structured data found. AI-search engines and rich-result generators "
            "rely on schema.org markup."
        )
    elif invalid_blocks > 0:
        finding["severity"] = "medium"
        finding["message"] = (
            f"{invalid_blocks} JSON-LD block(s) failed to parse. Validate at "
            "https://validator.schema.org."
        )
    else:
        finding["severity"] = "ok"
        finding["message"] = (
            f"Structured data present: {', '.join(types_unique) or 'unspecified types'}."
        )
    return finding
