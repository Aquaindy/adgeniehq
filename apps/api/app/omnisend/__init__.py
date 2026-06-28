"""Omnisend journey connection (Phase 5).

`journeys.py` holds the catalog of core nurture-flow types (reference data) that
the AI Omnisend Journey Builder turns into full, ready-to-build blueprints, and
that the traffic→Omnisend mapping uses to name segments/tags/flows.

Honest API boundary: Omnisend's public API is tag-based — it cannot *create*
automations or segments. So journeys are generated as blueprints the operator
builds once in Omnisend (triggered by a tag), while contact tagging + the
naming convention are applied for real via the existing autoresponder path.
"""
