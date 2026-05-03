"""Email-report foundation.

`build_report_email_body()` produces an HTML body and plain-text fallback from
a report payload. `send_email()` is a foundation: when SMTP env vars are
configured we send via stdlib smtplib; otherwise we structure-log the message
so the integration is real and testable, just unattached to a transport. M11+
can plug in SendGrid / Postmark / etc."""

from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any

from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class EmailMessageDraft:
    subject: str
    text_body: str
    html_body: str
    # Optional Reply-To header. Outreach uses this to route replies back to a
    # parse webhook keyed on a per-message token.
    reply_to: str | None = None


def build_report_email_body(payload: dict[str, Any], *, title: str) -> EmailMessageDraft:
    workspace = (payload.get("workspace") or {}).get("name") or "your workspace"
    period = payload.get("period") or {}
    summary = payload.get("summary") or {}
    rec_status = summary.get("recommendations_by_status", {})
    rec_risk = summary.get("recommendations_by_risk", {})
    top_recs = payload.get("top_recommendations") or []

    lines: list[str] = [
        f"AdVanta AI {period.get('label') or period.get('type', '')} Report",
        f"Workspace: {workspace}",
        f"Window: {(period.get('start') or '')[:10]} → {(period.get('end') or '')[:10]}",
        "",
        f"Agent runs: {summary.get('agent_runs_total', 0)}",
        f"Open recommendations: {rec_status.get('open', 0)} ({rec_risk.get('high', 0)} high risk)",
        f"Approved: {rec_status.get('approved', 0)}  ·  Rejected: {rec_status.get('rejected', 0)}",
        f"Campaigns total / active: {summary.get('campaigns_total', 0)} / {summary.get('campaigns_active', 0)}",
        f"Landing pages audited: {summary.get('landing_pages_audited', 0)}",
        f"Keywords tracked: {summary.get('keywords_tracked', 0)}",
        "",
    ]
    if top_recs:
        lines.append("Top recommendations:")
        for r in top_recs[:5]:
            lines.append(
                f"  - [{(r.get('risk_level') or '').upper()}] {r.get('title', '')}"
            )
        lines.append("")

    text_body = "\n".join(lines)

    html_rows: list[str] = []
    for r in top_recs[:5]:
        html_rows.append(
            f"<li><strong>[{(r.get('risk_level') or '').upper()}]</strong> "
            f"{r.get('title', '')}</li>"
        )
    rec_html = (
        f"<h3 style='color:#3E2F84;'>Top recommendations</h3><ul>{''.join(html_rows)}</ul>"
        if html_rows
        else ""
    )

    html_body = f"""
    <html><body style="font-family: -apple-system, sans-serif; color: #111827; max-width: 640px;">
      <h2 style="color:#3E2F84;">{title}</h2>
      <p style="color:#64748B;">Workspace: {workspace} · {(period.get('start') or '')[:10]} → {(period.get('end') or '')[:10]}</p>
      <h3 style="color:#3E2F84;">At a glance</h3>
      <ul>
        <li>Agent runs: <strong>{summary.get('agent_runs_total', 0)}</strong></li>
        <li>Open recs: <strong>{rec_status.get('open', 0)}</strong> ({rec_risk.get('high', 0)} high risk)</li>
        <li>Campaigns total / active: <strong>{summary.get('campaigns_total', 0)} / {summary.get('campaigns_active', 0)}</strong></li>
        <li>Landing pages audited: <strong>{summary.get('landing_pages_audited', 0)}</strong></li>
        <li>Keywords tracked: <strong>{summary.get('keywords_tracked', 0)}</strong></li>
      </ul>
      {rec_html}
      <p style="color:#94A3B8; font-size: 12px; margin-top: 24px;">
        Every figure is computed from real workspace data. Empty sections mean the underlying
        data is not yet available.
      </p>
    </body></html>
    """.strip()

    return EmailMessageDraft(subject=title, text_body=text_body, html_body=html_body)


def send_email(*, to: str, draft: EmailMessageDraft) -> bool:
    """Send via SMTP if `SMTP_HOST` is configured; otherwise log the draft and
    return False. Returns True on a successful SMTP send.

    Env vars: SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASSWORD,
    SMTP_FROM. SMTP_TLS=1 (default) uses STARTTLS."""
    host = os.getenv("SMTP_HOST", "").strip()
    if not host:
        log.info(
            "email.dropped.smtp_not_configured",
            to=to,
            subject=draft.subject,
        )
        return False

    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_FROM") or username or "no-reply@advantaai.com"
    use_tls = os.getenv("SMTP_TLS", "1") == "1"

    msg = EmailMessage()
    msg["Subject"] = draft.subject
    msg["From"] = sender
    msg["To"] = to
    if draft.reply_to:
        msg["Reply-To"] = draft.reply_to
    msg.set_content(draft.text_body)
    msg.add_alternative(draft.html_body, subtype="html")

    try:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            if use_tls:
                smtp.starttls()
            if username and password:
                smtp.login(username, password)
            smtp.send_message(msg)
    except Exception as exc:
        log.warning("email.send_failed", to=to, error=str(exc))
        return False

    log.info("email.sent", to=to, subject=draft.subject)
    return True
