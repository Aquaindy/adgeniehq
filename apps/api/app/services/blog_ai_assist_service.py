"""Blog editor AI Assistant.

Five action-typed endpoints, all backed by the same `complete_metered`
pipeline as the rest of the app — token usage + dollar-cost are recorded
under the workspace's billing usage.

Each action returns a structured result the frontend can render and let the
user accept (insert / replace) or discard. The service never auto-writes
to the draft; that decision is the operator's, the same as for any agent
recommendation.

Actions:
  - outline           → returns a list of section headings + 1-line summaries
  - expand            → expands a heading or short bullet into a full paragraph
  - refine            → rewrites a passage for clarity / tone / length
  - suggest_title     → 5 candidate titles, scored by length suitability
  - suggest_meta      → meta_title (≤60 chars) + meta_description (≤155 chars)

When no LLM is configured (or the call fails), each action falls back to a
deterministic stub — always non-empty so the UI doesn't dead-end. Tests
exercise the stub path so the assistant remains testable without an API key.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.llm.client import LlmError, LlmMessage, get_llm_client_for_workspace
from app.models.content_draft import ContentDraft
from app.models.onboarding_profile import OnboardingProfile


_VALID_ACTIONS = {"outline", "expand", "refine", "suggest_title", "suggest_meta"}


class UnknownAssistActionError(AdVantaError):
    status_code = 422
    code = "unknown_assist_action"


def assist(
    db: Session,
    *,
    workspace_id: UUID,
    draft: ContentDraft,
    action: str,
    selection: str | None,
    instructions: str | None,
) -> dict[str, Any]:
    """Run a single AI-Assistant action and return its result. The caller
    is the route layer; permissions are enforced there."""

    if action not in _VALID_ACTIONS:
        raise UnknownAssistActionError(
            f"Unknown action '{action}'. Valid: {sorted(_VALID_ACTIONS)}."
        )

    profile = (
        db.query(OnboardingProfile)
        .filter(OnboardingProfile.workspace_id == workspace_id)
        .first()
    )

    llm = get_llm_client_for_workspace(db, workspace_id)
    if llm.is_configured():
        try:
            result, source = (
                _via_llm(
                    db,
                    workspace_id=workspace_id,
                    draft=draft,
                    profile=profile,
                    action=action,
                    selection=selection,
                    instructions=instructions,
                ),
                "llm",
            )
            return {"action": action, "source": source, "result": result}
        except (LlmError, AdVantaError):
            # Fall through to deterministic stub.
            pass

    return {
        "action": action,
        "source": "deterministic",
        "result": _deterministic(
            draft=draft,
            action=action,
            selection=selection,
            instructions=instructions,
        ),
    }


# -------------------------------------------------------------------------
# LLM-backed paths
# -------------------------------------------------------------------------


def _via_llm(
    db: Session,
    *,
    workspace_id: UUID,
    draft: ContentDraft,
    profile: OnboardingProfile | None,
    action: str,
    selection: str | None,
    instructions: str | None,
) -> dict[str, Any]:
    llm = get_llm_client_for_workspace(db, workspace_id)
    system, user = _build_messages(
        draft=draft,
        profile=profile,
        action=action,
        selection=selection,
        instructions=instructions,
    )
    completion = llm.complete_metered(
        db=db,
        workspace_id=workspace_id,
        messages=[system, user],
        max_tokens=900,
        temperature=0.4,
        purpose=f"blog_assist.{action}",
    )
    return _parse_result(action=action, raw=completion.text)


def _build_messages(
    *,
    draft: ContentDraft,
    profile: OnboardingProfile | None,
    action: str,
    selection: str | None,
    instructions: str | None,
) -> tuple[LlmMessage, LlmMessage]:
    voice = (profile.brand_voice if profile else None) or "Confident, calm, executive."
    audience = (profile.target_audience if profile else None) or "—"

    base_context = (
        f"Brand voice: {voice}\n"
        f"Audience: {audience}\n"
        f"Post title: {draft.title or '(untitled)'}\n"
        f"Post body so far:\n{(draft.body or '').strip()[:6000]}\n"
    )

    if action == "outline":
        system = (
            "You are a senior B2B blog editor. Return a JSON object: "
            '{"sections": [{"heading": str, "summary": str}, ...]} with 5–8 '
            "sections. Each summary is one sentence. Return JSON only."
        )
        user_text = base_context + (
            "\nWriter's instructions for the outline: "
            + (instructions or "(none)")
        )
    elif action == "expand":
        if not selection:
            raise UnknownAssistActionError(
                "expand requires a selection (heading or bullet)."
            )
        system = (
            "You are a senior B2B blog editor. Expand the selected heading or "
            "bullet into a single paragraph that fits the brand voice. Return "
            'JSON: {"paragraph": str}. Keep it under 180 words.'
        )
        user_text = base_context + (
            f"\nSelection to expand:\n{selection}\n"
            f"\nWriter's instructions: {instructions or '(none)'}"
        )
    elif action == "refine":
        if not selection:
            raise UnknownAssistActionError(
                "refine requires a selection (the passage to rewrite)."
            )
        system = (
            "You are a senior B2B blog editor. Rewrite the selected passage "
            "for clarity, tone, and length per the writer's instructions. "
            'Return JSON: {"passage": str}. Preserve any links / formatting '
            "the writer used."
        )
        user_text = base_context + (
            f"\nPassage to rewrite:\n{selection}\n"
            f"\nWriter's instructions: {instructions or 'tighten + clarify'}"
        )
    elif action == "suggest_title":
        system = (
            "You are a senior B2B blog editor. Propose 5 candidate titles "
            "for the post. Each candidate should be under 70 characters. "
            'Return JSON: {"candidates": [str, ...]}.'
        )
        user_text = base_context + (
            "\nWriter's instructions: " + (instructions or "(none)")
        )
    else:  # suggest_meta
        system = (
            "You are a senior B2B blog SEO editor. Produce a meta_title (≤60 "
            'chars) and meta_description (≤155 chars). Return JSON: '
            '{"meta_title": str, "meta_description": str}. Both must be '
            "compelling on a SERP."
        )
        user_text = base_context + (
            "\nWriter's instructions: " + (instructions or "(none)")
        )

    return (
        LlmMessage(role="system", content=system),
        LlmMessage(role="user", content=user_text + "\n\nReturn JSON only."),
    )


def _parse_result(*, action: str, raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LlmError(f"Assist LLM returned non-JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise LlmError("Assist LLM did not return a JSON object.")
    return data


# -------------------------------------------------------------------------
# Deterministic fallback — keeps the UI usable without an API key.
# -------------------------------------------------------------------------


def _deterministic(
    *,
    draft: ContentDraft,
    action: str,
    selection: str | None,
    instructions: str | None,
) -> dict[str, Any]:
    """Conservative skeletons. Always non-empty so the UI flow doesn't
    dead-end; clearly tagged as `[edit me]` so an operator doesn't ship
    them as-is. Mirrors the deterministic fallback used elsewhere in the
    skill stack (creative_strategy, content refresh)."""

    title = draft.title or "Untitled post"

    if action == "outline":
        return {
            "sections": [
                {"heading": "Why this matters", "summary": "[edit me] Open with the stake."},
                {"heading": "What to know first", "summary": "[edit me] Frame the prerequisite the reader needs."},
                {"heading": "How AdVanta handles it", "summary": "[edit me] Concrete behavior, named."},
                {"heading": "Pitfalls", "summary": "[edit me] What teams get wrong on first attempts."},
                {"heading": "Worked example", "summary": "[edit me] Walk through one real scenario."},
                {"heading": "Takeaways", "summary": "[edit me] Three sentences max."},
            ]
        }
    if action == "expand":
        seed = (selection or "").strip() or title
        return {
            "paragraph": (
                f"[edit me] Expanding on \"{seed[:120]}\": this is the part "
                "where you pin down the specific claim, name the platform "
                "behavior, and tie it back to a measurable outcome."
            )
        }
    if action == "refine":
        seed = (selection or "").strip()
        return {
            "passage": (
                f"[edit me] Tightened: {seed[:480]}"
                if seed
                else "[edit me] Provide a selection to rewrite."
            )
        }
    if action == "suggest_title":
        base = title.replace("[edit me] ", "").strip() or "Topic"
        return {
            "candidates": [
                f"How AdVanta handles {base.lower()}",
                f"{base}: a working playbook",
                f"What we learned about {base.lower()}",
                f"The {base.lower()} checklist",
                f"Notes on {base.lower()}",
            ]
        }
    # suggest_meta
    return {
        "meta_title": title[:60] or "AdVanta blog post",
        "meta_description": (
            f"[edit me] {title}. A short, SERP-optimized summary goes here — "
            "stay under 155 characters."
        )[:155],
    }
