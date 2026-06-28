"""Omnisend journey catalog — the core nurture flows (reference data).

Each journey type seeds the AI Omnisend Journey Builder with a sensible default
trigger, channel and step skeleton. The agent expands these into full blueprints
(subjects, body, delays, CTAs, exit conditions). Adding a type here makes it
selectable in the journey builder.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class JourneyStep:
    label: str
    delay: str  # human delay, e.g. "Immediately", "1 day", "3 days"


@dataclass(frozen=True)
class JourneyType:
    slug: str
    name: str
    description: str
    default_channel: str  # "email" | "email_sms"
    trigger: str
    recommended_for: list[str]
    default_steps: list[JourneyStep] = field(default_factory=list)


def _s(label: str, delay: str) -> JourneyStep:
    return JourneyStep(label=label, delay=delay)


JOURNEY_TYPES: list[JourneyType] = [
    JourneyType(
        "welcome", "Welcome sequence",
        "Introduce new subscribers, set expectations, and deliver first value.",
        "email", "Contact added with the campaign tag",
        ["All new subscribers", "Newsletter", "Lead magnet opt-ins"],
        [_s("Welcome + what to expect", "Immediately"), _s("Best resource / quick win", "1 day"),
         _s("Story + soft introduction to the offer", "3 days"), _s("Invitation / CTA", "5 days")],
    ),
    JourneyType(
        "lead_magnet", "Lead magnet delivery",
        "Deliver the lead magnet, then nurture toward the core offer.",
        "email", "Contact opts in for a lead magnet",
        ["Lead gen", "Solo ads", "Paid social", "SEO content"],
        [_s("Deliver the lead magnet", "Immediately"), _s("How to get the most from it", "1 day"),
         _s("Problem awareness", "2 days"), _s("Introduce the offer", "4 days"),
         _s("FAQ / objection handling", "6 days")],
    ),
    JourneyType(
        "webinar_registration", "Webinar registration follow-up",
        "Confirm the registration and build anticipation before the event.",
        "email_sms", "Contact registers for the webinar",
        ["Webinars", "Coaching", "High-ticket", "SaaS demos"],
        [_s("Confirm registration + add to calendar", "Immediately"),
         _s("What you'll learn", "1 day"), _s("Why it matters now", "2 days")],
    ),
    JourneyType(
        "webinar_reminder", "Webinar reminder flow",
        "Drive attendance with timely reminders across email + SMS.",
        "email_sms", "Approaching the webinar start time",
        ["Webinars", "Live launches", "Events"],
        [_s("1 day before", "-1 day"), _s("1 hour before", "-1 hour"),
         _s("We're live — join now", "At start")],
    ),
    JourneyType(
        "webinar_replay", "Replay follow-up flow",
        "Send the replay and convert attendees + no-shows.",
        "email", "Webinar ends",
        ["Webinars", "Launches", "Courses"],
        [_s("Replay is ready", "Immediately"), _s("Key takeaway + offer", "1 day"),
         _s("Objection handling", "2 days"), _s("Replay + bonus expires", "3 days")],
    ),
    JourneyType(
        "abandoned_cart", "Abandoned cart flow",
        "Recover checkouts that didn't complete.",
        "email_sms", "Checkout started but not completed",
        ["Ecommerce", "Digital products", "Memberships"],
        [_s("You left something behind", "1 hour"), _s("Still thinking it over?", "1 day"),
         _s("Last chance / incentive", "2 days")],
    ),
    JourneyType(
        "saas_trial", "SaaS trial onboarding",
        "Activate trial users and convert them to paid.",
        "email", "User starts a free trial",
        ["SaaS", "Apps", "Tools"],
        [_s("Welcome + first action", "Immediately"), _s("Core use case #1", "1 day"),
         _s("Core use case #2", "3 days"), _s("Trial ending + upgrade", "Before trial end"),
         _s("Last day of trial", "Trial end")],
    ),
    JourneyType(
        "product_education", "Product education sequence",
        "Teach buyers to get value so they stick and refer.",
        "email", "Contact buys or activates",
        ["SaaS", "Courses", "Ecommerce"],
        [_s("Getting started", "Immediately"), _s("Feature / benefit deep-dive", "2 days"),
         _s("Tips + best practices", "5 days")],
    ),
    JourneyType(
        "re_engagement", "Re-engagement campaign",
        "Win back subscribers who've gone quiet before they churn.",
        "email", "No opens/clicks in 60+ days",
        ["All lists", "Newsletters", "Ecommerce"],
        [_s("We miss you + best content", "Immediately"), _s("Incentive to come back", "3 days"),
         _s("Last email before cleanup", "6 days")],
    ),
    JourneyType(
        "referral", "Referral campaign",
        "Turn happy customers into a traffic source.",
        "email", "Customer reaches a positive milestone",
        ["SaaS", "Ecommerce", "Communities"],
        [_s("Invite + reward explainer", "Immediately"), _s("Reminder + share link", "3 days")],
    ),
    JourneyType(
        "post_purchase", "Post-purchase sequence",
        "Confirm, onboard, and set up the next purchase.",
        "email_sms", "Order placed",
        ["Ecommerce", "Digital products"],
        [_s("Order confirmation", "Immediately"), _s("How to use / what's next", "2 days"),
         _s("Review request", "7 days"), _s("Cross-sell / replenish", "14 days")],
    ),
    JourneyType(
        "solo_ads_nurture", "Solo ads lead nurture",
        "Warm cold solo-ad leads with value before selling.",
        "email", "Contact added with a Solo Ads vendor tag",
        ["Solo ads", "Paid email traffic", "Affiliate"],
        [_s("Deliver lead magnet + set expectations", "Immediately"),
         _s("Problem awareness", "1 day"), _s("Story-based trust", "2 days"),
         _s("Introduce the offer", "3 days"), _s("FAQ / objections", "4 days"),
         _s("Bonus / urgency", "5 days"), _s("Final reminder", "6 days")],
    ),
    JourneyType(
        "newsletter_nurture", "Newsletter subscriber nurture",
        "Keep newsletter subscribers engaged and primed to buy.",
        "email", "Contact subscribes to the newsletter",
        ["Newsletters", "Content brands", "Creators"],
        [_s("Welcome + best issues", "Immediately"), _s("Your story / why this newsletter", "3 days"),
         _s("Soft offer / what you sell", "7 days")],
    ),
]

JOURNEY_BY_SLUG: dict[str, JourneyType] = {j.slug: j for j in JOURNEY_TYPES}


def step_to_dict(s: JourneyStep) -> dict:
    return {"label": s.label, "delay": s.delay}


def journey_type_to_dict(j: JourneyType) -> dict:
    return {
        "slug": j.slug,
        "name": j.name,
        "description": j.description,
        "default_channel": j.default_channel,
        "trigger": j.trigger,
        "recommended_for": list(j.recommended_for),
        "default_steps": [step_to_dict(s) for s in j.default_steps],
    }


def journey_types_payload() -> list[dict]:
    return [journey_type_to_dict(j) for j in JOURNEY_TYPES]
