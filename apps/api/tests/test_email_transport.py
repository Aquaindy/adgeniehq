"""Email transport selection: Resend (preferred) → SMTP → log-drop."""

from __future__ import annotations

import app.services.email_service as es


def _draft() -> es.EmailMessageDraft:
    return es.EmailMessageDraft(
        subject="Hello", text_body="plain", html_body="<p>html</p>"
    )


def test_send_via_resend_posts_and_returns_true(monkeypatch) -> None:
    captured: dict = {}

    class _Resp:
        status_code = 202
        text = "{}"

    def _fake_post(url, headers=None, json=None, timeout=None):
        captured.update(url=url, headers=headers, json=json)
        return _Resp()

    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("EMAIL_FROM", "AdVanta <admin@aimarketinghub.io>")
    monkeypatch.setattr("httpx.post", _fake_post)

    assert es.send_email(to="user@example.com", draft=_draft()) is True
    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["headers"]["Authorization"] == "Bearer re_test_key"
    assert captured["json"]["from"] == "AdVanta <admin@aimarketinghub.io>"
    assert captured["json"]["to"] == ["user@example.com"]
    assert captured["json"]["subject"] == "Hello"


def test_resend_rejection_falls_through_to_drop_without_smtp(monkeypatch) -> None:
    class _Resp:
        status_code = 422
        text = "domain not verified"

    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.setattr("httpx.post", lambda *a, **k: _Resp())

    # Resend was configured but rejected; with no SMTP fallback the send fails.
    assert es.send_email(to="user@example.com", draft=_draft()) is False


def test_no_transport_logs_and_returns_false(monkeypatch) -> None:
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)

    assert es.send_email(to="user@example.com", draft=_draft()) is False


def test_email_from_falls_back_to_default(monkeypatch) -> None:
    monkeypatch.delenv("EMAIL_FROM", raising=False)
    monkeypatch.delenv("SMTP_FROM", raising=False)
    assert es._sender() == "AdVanta <noreply@getadvanta.app>"
