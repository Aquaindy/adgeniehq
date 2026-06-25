"""Render report payloads to PDF (reportlab) and CSV bytes."""

from __future__ import annotations

import csv
from io import BytesIO, StringIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


GRAPE = colors.HexColor("#3E2F84")
GRAPE_SOFT = colors.HexColor("#EEEAFE")
INK = colors.HexColor("#111827")
SLATE_400 = colors.HexColor("#94A3B8")
SLATE_500 = colors.HexColor("#64748B")
SLATE_700 = colors.HexColor("#334155")
SLATE_100 = colors.HexColor("#F1F5F9")


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def render_pdf(payload: dict[str, Any], *, title: str) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        title=title,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
    )
    story = []
    styles = _styles()

    workspace = (payload.get("workspace") or {}).get("name") or "Workspace"
    period = payload.get("period") or {}

    story.append(Paragraph("AdVanta AI", styles["brand"]))
    story.append(Paragraph(title, styles["title"]))
    story.append(
        Paragraph(
            f"{workspace} · {period.get('label', period.get('type', ''))} · "
            f"{(period.get('start') or '')[:10]} → {(period.get('end') or '')[:10]}",
            styles["subtitle"],
        )
    )
    story.append(Spacer(1, 0.18 * inch))

    _summary_section(story, payload, styles)
    _top_recommendations_section(story, payload, styles)
    _agent_runs_section(story, payload, styles)
    _campaigns_section(story, payload, styles)
    _ad_performance_section(story, payload, styles)
    _seo_section(story, payload, styles)
    _landing_pages_section(story, payload, styles)
    _executions_section(story, payload, styles)
    _content_drafts_section(story, payload, styles)
    _outreach_section(story, payload, styles)
    _ab_tests_section(story, payload, styles)
    _growth_dna_section(story, payload, styles)

    story.append(Spacer(1, 0.25 * inch))
    story.append(
        Paragraph(
            "Every figure in this report is computed from real workspace data. "
            "Empty sections mean the underlying data is not yet available.",
            styles["footer"],
        )
    )

    doc.build(story)
    return buffer.getvalue()


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["Normal"]
    return {
        "brand": ParagraphStyle(
            "brand",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=10,
            textColor=GRAPE,
            spaceAfter=2,
            leading=12,
        ),
        "title": ParagraphStyle(
            "title",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=18,
            textColor=INK,
            spaceAfter=2,
            leading=22,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            parent=base,
            fontName="Helvetica",
            fontSize=9,
            textColor=SLATE_500,
            leading=12,
        ),
        "section": ParagraphStyle(
            "section",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=12,
            textColor=GRAPE,
            spaceBefore=12,
            spaceAfter=4,
            leading=14,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base,
            fontName="Helvetica",
            fontSize=9.5,
            textColor=SLATE_700,
            leading=13,
        ),
        "muted": ParagraphStyle(
            "muted",
            parent=base,
            fontName="Helvetica",
            fontSize=8.5,
            textColor=SLATE_500,
            leading=11,
        ),
        "footer": ParagraphStyle(
            "footer",
            parent=base,
            fontName="Helvetica-Oblique",
            fontSize=8,
            textColor=SLATE_400,
            leading=11,
        ),
    }


def _summary_section(story: list, payload: dict[str, Any], styles: dict) -> None:
    summary = payload.get("summary") or {}
    if not summary:
        return
    story.append(Paragraph("At a glance", styles["section"]))

    rec_status = summary.get("recommendations_by_status", {})
    rec_risk = summary.get("recommendations_by_risk", {})

    rows = [
        ["Agent runs in period", summary.get("agent_runs_total", 0)],
        ["Open recommendations", rec_status.get("open", 0)],
        ["Approved recommendations", rec_status.get("approved", 0)],
        ["Rejected recommendations", rec_status.get("rejected", 0)],
        ["High-risk recs", rec_risk.get("high", 0)],
        ["Campaigns total / active", f"{summary.get('campaigns_total', 0)} / {summary.get('campaigns_active', 0)}"],
        ["Landing pages audited", summary.get("landing_pages_audited", 0)],
        ["Keywords tracked", summary.get("keywords_tracked", 0)],
    ]
    table = Table(rows, colWidths=[2.5 * inch, 4.5 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("TEXTCOLOR", (0, 0), (0, -1), SLATE_500),
                ("TEXTCOLOR", (1, 0), (1, -1), INK),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, SLATE_100),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(table)


def _top_recommendations_section(story: list, payload: dict[str, Any], styles: dict) -> None:
    recs = payload.get("top_recommendations") or []
    story.append(Paragraph("Top open recommendations", styles["section"]))
    if not recs:
        story.append(
            Paragraph(
                "No open recommendations in the period — either none were generated or "
                "all of them have been actioned.",
                styles["muted"],
            )
        )
        return

    rows = [["Risk", "Title", "Suggested action"]]
    for r in recs:
        rows.append(
            [
                (r.get("risk_level") or "").upper(),
                _truncate(r.get("title"), 60),
                _truncate(r.get("suggested_action"), 100),
            ]
        )
    table = Table(rows, colWidths=[0.7 * inch, 2.7 * inch, 3.6 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), GRAPE_SOFT),
                ("TEXTCOLOR", (0, 0), (-1, 0), GRAPE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, SLATE_100),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(table)


def _agent_runs_section(story: list, payload: dict[str, Any], styles: dict) -> None:
    runs = payload.get("agent_runs") or []
    story.append(Paragraph("Agent activity", styles["section"]))
    if not runs:
        story.append(Paragraph("No agent runs in the period.", styles["muted"]))
        return
    rows = [["Agent", "Status", "Recs", "Started"]]
    for r in runs:
        rows.append(
            [
                r.get("agent_type", ""),
                r.get("status", ""),
                str(r.get("recommendation_count", 0)),
                (r.get("started_at") or "")[:19].replace("T", " "),
            ]
        )
    table = Table(rows, colWidths=[2.0 * inch, 1.0 * inch, 0.7 * inch, 3.3 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), SLATE_100),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, SLATE_100),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)


def _campaigns_section(story: list, payload: dict[str, Any], styles: dict) -> None:
    block = payload.get("campaigns") or {}
    if not block.get("total"):
        return
    story.append(Paragraph("Paid ads", styles["section"]))
    rows = [["Total", str(block.get("total", 0))]]
    for provider, count in (block.get("per_provider") or {}).items():
        rows.append([provider, str(count)])
    rows.append(["Active without budget", str(block.get("active_without_budget", 0))])
    rows.append(["Stale active", str(block.get("stale_active", 0))])
    table = Table(rows, colWidths=[2.5 * inch, 4.5 * inch])
    table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, SLATE_100),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(table)


def _seo_section(story: list, payload: dict[str, Any], styles: dict) -> None:
    seo = payload.get("seo") or {}
    if not seo.get("present"):
        return
    story.append(Paragraph("SEO & GEO", styles["section"]))
    if seo.get("site_url"):
        story.append(Paragraph(f"Site: {seo['site_url']}", styles["body"]))
    if seo.get("last_crawled_at"):
        story.append(
            Paragraph(
                f"Last crawled: {seo['last_crawled_at'][:19].replace('T', ' ')} UTC",
                styles["muted"],
            )
        )
    keywords = seo.get("top_keywords") or []
    if keywords:
        rows = [["Query", "Impr.", "Clicks", "Pos.", "Opp."]]
        for kw in keywords:
            rows.append(
                [
                    _truncate(kw.get("query"), 45),
                    str(kw.get("impressions", 0)),
                    str(kw.get("clicks", 0)),
                    f"{kw.get('position', 0):.1f}",
                    str(kw.get("opportunity_score", 0)),
                ]
            )
        table = Table(rows, colWidths=[3.4 * inch, 0.9 * inch, 0.7 * inch, 0.7 * inch, 0.7 * inch])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), SLATE_100),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, SLATE_100),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(table)


def _landing_pages_section(story: list, payload: dict[str, Any], styles: dict) -> None:
    pages = payload.get("landing_pages") or []
    if not pages:
        return
    story.append(Paragraph("Landing pages", styles["section"]))
    rows = [["URL", "Conv.", "Mobile", "Speed"]]
    for p in pages:
        scores = p.get("scores") or {}
        rows.append(
            [
                _truncate(p.get("url"), 60),
                str(scores.get("conversion") if scores.get("conversion") is not None else "—"),
                str(scores.get("mobile_ux") if scores.get("mobile_ux") is not None else "—"),
                str(scores.get("page_speed") if scores.get("page_speed") is not None else "—"),
            ]
        )
    table = Table(rows, colWidths=[4.4 * inch, 0.7 * inch, 0.8 * inch, 0.7 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), SLATE_100),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, SLATE_100),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)


def _kv_table(rows: list[list[str]]) -> Table:
    """Standard key/value table used by the post-M12 sections."""
    table = Table(rows, colWidths=[2.5 * inch, 4.5 * inch])
    table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), SLATE_500),
                ("TEXTCOLOR", (1, 0), (1, -1), INK),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, SLATE_100),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _executions_section(story: list, payload: dict[str, Any], styles: dict) -> None:
    block = payload.get("executions") or {}
    if not block.get("total"):
        return
    story.append(Paragraph("Provider writes", styles["section"]))
    rows: list[list[str]] = [["Total", str(block.get("total", 0))]]
    by_status = block.get("by_status") or {}
    for status_name in ("succeeded", "failed", "pending", "running", "reverted"):
        if by_status.get(status_name):
            rows.append([status_name.capitalize(), str(by_status[status_name])])
    by_provider = block.get("by_provider") or {}
    for provider, count in by_provider.items():
        rows.append([f"Provider: {provider}", str(count)])
    story.append(_kv_table(rows))


def _content_drafts_section(story: list, payload: dict[str, Any], styles: dict) -> None:
    block = payload.get("content_drafts") or {}
    if not block.get("total"):
        return
    story.append(Paragraph("Content drafts", styles["section"]))
    rows: list[list[str]] = [["Total drafts", str(block.get("total", 0))]]
    by_status = block.get("by_status") or {}
    for status_name in ("draft", "approved", "published", "archived"):
        if by_status.get(status_name):
            rows.append([status_name.capitalize(), str(by_status[status_name])])
    by_type = block.get("by_type") or {}
    for type_name, count in by_type.items():
        rows.append([f"Type: {type_name}", str(count)])
    story.append(_kv_table(rows))


def _outreach_section(story: list, payload: dict[str, Any], styles: dict) -> None:
    block = payload.get("outreach") or {}
    if not block.get("emails_total") and not block.get("prospects_total"):
        return
    story.append(Paragraph("Backlink outreach", styles["section"]))
    reply_rate = block.get("reply_rate") or 0.0
    rows: list[list[str]] = [
        ["Emails sent", str(block.get("emails_sent", 0))],
        ["Replies", str(block.get("emails_replied", 0))],
        ["Bounces", str(block.get("emails_bounced", 0))],
        ["Reply rate", f"{reply_rate * 100:.1f}%"],
        ["Prospects", str(block.get("prospects_total", 0))],
        ["Won (linked)", str(block.get("prospects_won", 0))],
    ]
    story.append(_kv_table(rows))


def _ab_tests_section(story: list, payload: dict[str, Any], styles: dict) -> None:
    block = payload.get("ab_tests") or {}
    if not block.get("total"):
        return
    story.append(Paragraph("A/B tests", styles["section"]))
    rows: list[list[str]] = [["Total tests", str(block.get("total", 0))]]
    by_status = block.get("by_status") or {}
    for status_name in ("draft", "ready", "launched", "paused", "completed", "archived"):
        if by_status.get(status_name):
            rows.append([status_name.capitalize(), str(by_status[status_name])])
    rows.append(
        ["Completed with winner", str(block.get("completed_with_winner", 0))]
    )
    story.append(_kv_table(rows))


def _ad_performance_section(story: list, payload: dict[str, Any], styles: dict) -> None:
    ap = payload.get("ad_performance")
    if not ap:
        return
    story.append(Paragraph("Ad performance", styles["section"]))

    def _money(c: int) -> str:
        return f"${c / 100:,.2f}"

    rows = [
        ["Metric", "Value"],
        ["Spend", _money(ap.get("spend_cents", 0))],
        ["Impressions", f"{ap.get('impressions', 0):,}"],
        ["Clicks", f"{ap.get('clicks', 0):,}"],
        ["Conversions", f"{ap.get('conversions', 0):,}"],
        ["CTR", f"{ap.get('ctr', 0) * 100:.2f}%"],
        ["CPA", _money(ap.get("cpa_cents", 0)) if ap.get("conversions") else "—"],
        ["ROAS", f"{ap.get('roas', 0):.2f}x" if ap.get("spend_cents") else "—"],
    ]
    story.append(_kv_table(rows))


def _growth_dna_section(story: list, payload: dict[str, Any], styles: dict) -> None:
    dna = payload.get("growth_dna")
    if not dna:
        return
    story.append(Paragraph("Growth DNA", styles["section"]))
    story.append(
        Paragraph(
            f"Funnel readiness: {dna.get('funnel_readiness_score', 0)} / 100 · "
            f"Paid ads readiness: {dna.get('paid_ads_readiness_score', 0)} / 100 · "
            f"engine {dna.get('engine_version')}",
            styles["body"],
        )
    )
    channel_count = dna.get("channel_count")
    if channel_count:
        priorities = dna.get("top_priorities") or []
        line = f"Marketing strategy: {channel_count} channels mapped"
        if priorities:
            line += " · Top priorities: " + ", ".join(str(p) for p in priorities[:4])
        story.append(Paragraph(line, styles["body"]))


def _truncate(value: str | None, max_len: int) -> str:
    if not value:
        return ""
    text = " ".join(str(value).split())
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


# ---------------------------------------------------------------------------
# CSV (recommendations)
# ---------------------------------------------------------------------------


def render_csv(payload: dict[str, Any]) -> bytes:
    """Multi-section CSV. Each section is preceded by a header row prefixed
    with `# <section>` so a downstream parser can split easily, and the
    blank rows between sections act as a visual separator in spreadsheets.

    Sections (in order, omitted if absent):
      - Top recommendations
      - Provider writes (executions)
      - Content drafts
      - Outreach (emails + prospects)
      - A/B tests
    """

    buffer = StringIO()
    writer = csv.writer(buffer)

    # ---- Top recommendations ------------------------------------------
    # Always emit the recommendations header — even on an empty workspace —
    # so downstream tools can rely on a predictable column layout.
    recs = payload.get("top_recommendations") or []
    writer.writerow(["# top_recommendations"])
    writer.writerow(
        [
            "risk_level",
            "title",
            "recommendation_type",
            "platform",
            "expected_impact",
            "suggested_action",
            "agent_run_id",
            "created_at",
        ]
    )
    for r in recs:
        writer.writerow(
            [
                r.get("risk_level"),
                r.get("title"),
                r.get("recommendation_type"),
                r.get("platform") or "",
                r.get("expected_impact"),
                r.get("suggested_action"),
                r.get("agent_run_id"),
                r.get("created_at"),
            ]
        )
    writer.writerow([])

    # ---- Provider writes (executions) ---------------------------------
    executions = payload.get("executions") or {}
    if executions.get("total"):
        writer.writerow(["# executions"])
        writer.writerow(["metric", "value"])
        writer.writerow(["total", executions.get("total", 0)])
        for status_name, count in (executions.get("by_status") or {}).items():
            writer.writerow([f"by_status.{status_name}", count])
        for provider, count in (executions.get("by_provider") or {}).items():
            writer.writerow([f"by_provider.{provider}", count])
        writer.writerow([])

    # ---- Content drafts -----------------------------------------------
    drafts = payload.get("content_drafts") or {}
    if drafts.get("total"):
        writer.writerow(["# content_drafts"])
        writer.writerow(["metric", "value"])
        writer.writerow(["total", drafts.get("total", 0)])
        for status_name, count in (drafts.get("by_status") or {}).items():
            writer.writerow([f"by_status.{status_name}", count])
        for type_name, count in (drafts.get("by_type") or {}).items():
            writer.writerow([f"by_type.{type_name}", count])
        writer.writerow([])

    # ---- Outreach -----------------------------------------------------
    outreach = payload.get("outreach") or {}
    if outreach.get("emails_total") or outreach.get("prospects_total"):
        writer.writerow(["# outreach"])
        writer.writerow(["metric", "value"])
        writer.writerow(["emails_total", outreach.get("emails_total", 0)])
        writer.writerow(["emails_sent", outreach.get("emails_sent", 0)])
        writer.writerow(["emails_replied", outreach.get("emails_replied", 0)])
        writer.writerow(["emails_bounced", outreach.get("emails_bounced", 0)])
        writer.writerow(["reply_rate", f"{outreach.get('reply_rate', 0.0):.4f}"])
        writer.writerow(["prospects_total", outreach.get("prospects_total", 0)])
        writer.writerow(["prospects_won", outreach.get("prospects_won", 0)])
        writer.writerow([])

    # ---- A/B tests ----------------------------------------------------
    ab_tests = payload.get("ab_tests") or {}
    if ab_tests.get("total"):
        writer.writerow(["# ab_tests"])
        writer.writerow(["metric", "value"])
        writer.writerow(["total", ab_tests.get("total", 0)])
        for status_name, count in (ab_tests.get("by_status") or {}).items():
            writer.writerow([f"by_status.{status_name}", count])
        writer.writerow(
            ["completed_with_winner", ab_tests.get("completed_with_winner", 0)]
        )
        writer.writerow([])

    return buffer.getvalue().encode("utf-8")
