"""Omnisend Journey Builder agent (Phase 5).

Turns a journey type + offer context into a complete, ready-to-build Omnisend
automation blueprint: flow name, trigger, segmentation rules, a full email
sequence (delay/subject/preheader/body/CTA/personalization tokens), an optional
SMS sequence, exit conditions, and the conversion goal.

Honest boundary: Omnisend's public API can't create automations, so the agent
also returns `implementation_notes` explaining how to build it once in Omnisend,
triggered by the campaign tag. The LLM writes the copy; a deterministic fallback
assembles the blueprint from the journey type's default steps when no LLM exists.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.agents.base import BaseAgent
from app.agents.types import AgentContext, AgentResult, SkillOutputRecord, TaskRecord
from app.models.agent_task import AgentTaskStatus
from app.omnisend import journeys as cat


class OmnisendJourneyAgent(BaseAgent):
    type = "omnisend_journey"
    title = "Omnisend journey builder"
    description = (
        "Generates a full Omnisend automation blueprint — trigger, segmentation, "
        "email + SMS sequence with delays/subjects/body/CTAs, exit conditions and "
        "the conversion goal — ready to build once in Omnisend."
    )

    def run(self, ctx: AgentContext) -> AgentResult:
        result = AgentResult()
        started = datetime.now(timezone.utc)
        inp = ctx.input_payload or {}

        slug = (inp.get("journey_type") or "welcome").strip()
        jtype = cat.JOURNEY_BY_SLUG.get(slug) or cat.JOURNEY_BY_SLUG["welcome"]
        channel = (inp.get("channel") or jtype.default_channel).strip()
        wants_sms = "sms" in channel

        enrich = self._llm_generate(ctx, jtype, channel, inp)
        blueprint = self._assemble(jtype, channel, wants_sms, inp, enrich)

        result.tasks.append(
            TaskRecord(
                skill_name="omnisend.journey",
                status=AgentTaskStatus.SUCCEEDED,
                input_payload={"journey_type": jtype.slug, "channel": channel},
                output_payload={"generation": blueprint["generation"], "steps": len(blueprint["email_sequence"])},
                started_at=started,
                completed_at=datetime.now(timezone.utc),
            )
        )
        result.skill_outputs.append(
            SkillOutputRecord(
                skill_name="omnisend.journey",
                output_type="omnisend_journey",
                payload=blueprint,
                task_index=1,
            )
        )
        result.output_payload = blueprint
        return result

    # ------------------------------------------------------------------

    def _assemble(self, jtype: cat.JourneyType, channel: str, wants_sms: bool, inp: dict, enrich: dict) -> dict:
        offer = inp.get("offer_name") or "your offer"
        flow_name = inp.get("flow_name") or self._default_flow_name(jtype, inp)
        email_sequence = enrich.get("email_sequence") or self._fallback_emails(jtype, inp)
        sms_sequence = (enrich.get("sms_sequence") if wants_sms else None) or (
            self._fallback_sms(jtype, inp) if wants_sms else []
        )
        return {
            "journey_type": jtype.slug,
            "journey_name": jtype.name,
            "flow_name": flow_name,
            "channel": channel,
            "trigger": enrich.get("trigger") or jtype.trigger,
            "segmentation_rules": enrich.get("segmentation_rules") or self._fallback_segmentation(inp),
            "generation": "llm" if enrich else "deterministic",
            "email_sequence": email_sequence,
            "sms_sequence": sms_sequence,
            "exit_conditions": enrich.get("exit_conditions") or self._fallback_exits(jtype),
            "conversion_goal": enrich.get("conversion_goal") or self._fallback_goal(jtype, offer),
            "implementation_notes": [
                "Omnisend's API can't create automations — build this once in Omnisend "
                "(Automations → Create workflow).",
                f"Trigger the workflow on the tag this campaign applies (e.g. the segment tag), "
                f"so contacts entering with that tag start the flow.",
                "Map each step below to an email/SMS node with the listed delay.",
                "Use Omnisend personalization tags (e.g. {{ contact.firstName }}) for the tokens shown.",
            ],
        }

    def _default_flow_name(self, jtype: cat.JourneyType, inp: dict) -> str:
        offer = inp.get("offer_name") or inp.get("campaign_name")
        return f"{jtype.name}" + (f" — {offer}" if offer else "")

    def _fallback_segmentation(self, inp: dict) -> str:
        tag = inp.get("tag") or inp.get("segment_name")
        if tag:
            return f"Contacts tagged '{tag}' (entered from this campaign)."
        return "Contacts who entered via this campaign's tag/segment."

    def _fallback_emails(self, jtype: cat.JourneyType, inp: dict) -> list[dict]:
        offer = inp.get("offer_name") or "your offer"
        url = inp.get("offer_url") or "[your link]"
        out: list[dict] = []
        for i, step in enumerate(jtype.default_steps, start=1):
            out.append({
                "step": i,
                "delay": step.delay,
                "subject": self._subject_for(step.label, offer),
                "preheader": f"{step.label} — a quick note inside.",
                "body": (
                    f"Hi {{{{ contact.firstName }}}},\n\n"
                    f"{step.label}.\n\n"
                    f"[Write 2-3 sentences here tailored to '{offer}'.]\n\n"
                    f"{url}\n\n"
                    "— [Your name]"
                ),
                "cta": "Take the next step →",
                "personalization_tokens": ["{{ contact.firstName }}"],
            })
        return out

    def _subject_for(self, label: str, offer: str) -> str:
        low = label.lower()
        if "deliver" in low or "welcome" in low or "confirm" in low:
            return f"Here's {offer} (as promised)"
        if "reminder" in low or "last" in low or "expire" in low or "final" in low:
            return "Quick reminder before this closes"
        if "story" in low or "trust" in low:
            return "The story behind this"
        if "offer" in low or "introduce" in low:
            return f"Ready for the next step with {offer}?"
        return label

    def _fallback_sms(self, jtype: cat.JourneyType, inp: dict) -> list[dict]:
        # SMS only for steps that benefit from immediacy (reminders / time-sensitive).
        msgs: list[dict] = []
        for step in jtype.default_steps:
            low = step.label.lower()
            if any(w in low for w in ("remind", "live", "before", "last", "confirm", "order")):
                msgs.append({
                    "delay": step.delay,
                    "message": f"{{{{ contact.firstName }}}}: {step.label}. Reply STOP to opt out.",
                })
        return msgs[:3]

    def _fallback_exits(self, jtype: cat.JourneyType) -> list[str]:
        exits = ["Contact converts (reaches the conversion goal)", "Contact unsubscribes"]
        if jtype.slug in ("abandoned_cart", "post_purchase", "saas_trial"):
            exits.append("Contact completes the target action (purchase/upgrade)")
        return exits

    def _fallback_goal(self, jtype: cat.JourneyType, offer: str) -> str:
        goals = {
            "abandoned_cart": "Completed checkout",
            "saas_trial": "Trial → paid conversion",
            "post_purchase": "Repeat purchase / review left",
            "referral": "Referral submitted",
            "webinar_registration": "Webinar attendance",
            "webinar_reminder": "Webinar attendance",
            "webinar_replay": f"Purchase of {offer}",
        }
        return goals.get(jtype.slug, f"Conversion on {offer}")

    # ------------------------------------------------------------------
    # LLM generation — deterministic fallback on failure
    # ------------------------------------------------------------------

    def _llm_generate(self, ctx: AgentContext, jtype: cat.JourneyType, channel: str, inp: dict) -> dict:
        from app.llm.client import LlmMessage, get_llm_client_for_workspace

        context = {
            "journey": jtype.name,
            "trigger": jtype.trigger,
            "channel": channel,
            "default_steps": [cat.step_to_dict(s) for s in jtype.default_steps],
            "offer_name": inp.get("offer_name"),
            "offer_url": inp.get("offer_url"),
            "audience": inp.get("audience"),
            "tag": inp.get("tag") or inp.get("segment_name"),
        }
        sms_clause = (
            " sms_sequence (array of {delay, message} — only for time-sensitive steps),"
            if "sms" in channel else " sms_sequence (empty array),"
        )
        system = (
            f"You are an email/SMS lifecycle strategist building an Omnisend automation. Return STRICT "
            "JSON only (no prose, no code fences) with keys: trigger (string), segmentation_rules "
            "(string), email_sequence (array of {step:int, delay:string, subject:string, preheader:string, "
            "body:string with newlines, cta:string, personalization_tokens:array of strings}),"
            + sms_clause +
            " exit_conditions (array of strings), conversion_goal (string). Use Omnisend personalization "
            "syntax like {{ contact.firstName }}. Keep copy benefit-driven and honest; no guarantees. "
            "Base the number/timing of steps on the provided default_steps."
        )
        user = "Journey context JSON:\n" + json.dumps({k: v for k, v in context.items() if v})
        try:
            client = get_llm_client_for_workspace(ctx.db, ctx.workspace_id)
            completion = client.complete_metered(
                db=ctx.db,
                workspace_id=ctx.workspace_id,
                messages=[LlmMessage(role="system", content=system), LlmMessage(role="user", content=user)],
                max_tokens=2400,
                temperature=0.5,
                purpose="omnisend_journey",
            )
            return _parse_json(completion.text)
        except Exception as exc:  # noqa: BLE001 — any LLM/budget failure → deterministic blueprint
            from app.core.logging import get_logger

            get_logger(__name__).info("omnisend_journey.llm_fallback", error=str(exc))
            return {}


def _parse_json(text: str) -> dict:
    body = (text or "").strip()
    if body.startswith("```"):
        lines = body.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        body = "\n".join(lines)
    if not body.startswith("{") and "{" in body:
        body = body[body.index("{"):]
    try:
        parsed = json.loads(body)
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}
