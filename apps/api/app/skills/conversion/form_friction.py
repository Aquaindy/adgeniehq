from bs4 import BeautifulSoup, Tag


def _is_visible_field(tag: Tag) -> bool:
    type_ = (tag.get("type") or "").lower()
    if type_ in {"hidden", "submit", "button", "reset", "image"}:
        return False
    return True


def check_form_friction(soup: BeautifulSoup) -> dict:
    forms = soup.find_all("form")
    form_summaries: list[dict] = []
    max_fields = 0

    for form in forms:
        fields = []
        for inp in form.find_all(["input", "select", "textarea"]):
            if not _is_visible_field(inp):
                continue
            label = (
                inp.get("aria-label")
                or inp.get("placeholder")
                or inp.get("name")
                or inp.get("id")
                or inp.name
            )
            fields.append({"tag": inp.name, "label": label, "type": inp.get("type")})
        max_fields = max(max_fields, len(fields))
        form_summaries.append({"field_count": len(fields), "fields": fields[:25]})

    if not forms:
        return {
            "form_count": 0,
            "forms": [],
            "max_fields": 0,
            "score": 100,  # no forms means no friction to penalize
            "severity": "ok",
            "message": "No forms detected on the page.",
        }

    # Score: 1-3 fields = 100, 4-6 = 75, 7-9 = 45, 10+ = 15
    if max_fields <= 3:
        score, severity, message = 100, "ok", "Forms are concise (≤3 visible fields)."
    elif max_fields <= 6:
        score, severity, message = (
            75,
            "low",
            f"Largest form has {max_fields} visible fields. Trim to the essentials if possible.",
        )
    elif max_fields <= 9:
        score, severity, message = (
            45,
            "medium",
            f"Largest form has {max_fields} fields — that's high friction for a top-of-funnel form.",
        )
    else:
        score, severity, message = (
            15,
            "high",
            f"Largest form has {max_fields} fields. Consider multi-step or lazy-collected fields.",
        )

    return {
        "form_count": len(forms),
        "forms": form_summaries,
        "max_fields": max_fields,
        "score": score,
        "severity": severity,
        "message": message,
    }
