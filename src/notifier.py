"""Email notification for new properties matching user-defined conditions.

Sends a digest email via Gmail SMTP when a fetch cycle discovers new
properties that satisfy the filter criteria set in ``NOTIFY_CONDITIONS``.
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import sqlite3
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def _load_conditions() -> dict:
    raw = os.environ.get("NOTIFY_CONDITIONS", "{}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"[notifier] invalid NOTIFY_CONDITIONS JSON: {raw!r}")
        return {}


def _matches(prop: dict, cond: dict) -> bool:
    rent = prop.get("rent", 0) or 0
    if "rent_max" in cond and rent > cond["rent_max"]:
        return False
    walk = prop.get("walk_minutes")
    if "walk_max" in cond and walk is not None and walk > cond["walk_max"]:
        return False
    size = prop.get("size_sqm")
    if "size_min" in cond and size is not None and size < cond["size_min"]:
        return False
    age = prop.get("building_age_years")
    if "age_max" in cond and age is not None and age > cond["age_max"]:
        return False
    layouts = cond.get("layouts")
    if layouts and prop.get("layout") and prop["layout"] not in layouts:
        return False
    return True


def get_new_matching(conn: sqlite3.Connection, since: str, cond: dict) -> list[dict]:
    """Return properties first_seen > ``since`` that match ``cond``."""
    rows = conn.execute(
        "SELECT data, first_seen FROM properties "
        "WHERE status = 'active' AND first_seen > ? "
        "ORDER BY first_seen DESC",
        (since,),
    ).fetchall()

    matched = []
    for data_json, first_seen in rows:
        try:
            prop = json.loads(data_json)
        except json.JSONDecodeError:
            continue
        prop["first_seen"] = first_seen
        if _matches(prop, cond):
            matched.append(prop)
    return matched


def _format_rent(yen: int) -> str:
    if yen >= 10000:
        man = yen / 10000
        return f"{man:.1f}万円" if yen % 10000 else f"{int(man)}万円"
    return f"{yen:,}円"


def build_email_html(properties: list[dict], conditions: dict) -> str:
    items_html = ""
    for p in properties[:30]:
        rent = _format_rent(p.get("rent", 0))
        mgmt = f" (+{_format_rent(p.get('management_fee', 0))})" if p.get("management_fee") else ""
        details = " / ".join(filter(None, [
            p.get("layout"),
            f"{p['size_sqm']}㎡" if p.get("size_sqm") else None,
            f"築{p['building_age_years']}年" if p.get("building_age_years") is not None else None,
        ]))
        station = f"{p.get('nearest_station', '')} 徒歩{p.get('walk_minutes', '?')}分"
        url = p.get("source_url", "")
        source = p.get("source", "")

        items_html += f"""
        <div style="border:1px solid #e0e0e0;border-left:4px solid #27ae60;border-radius:6px;padding:12px;margin-bottom:10px;">
            <div style="font-weight:700;font-size:14px;margin-bottom:4px;">{p.get('name', '')}</div>
            <div style="font-size:18px;font-weight:700;color:#e74c3c;">{rent}{mgmt}</div>
            <div style="font-size:13px;color:#666;margin-top:4px;">{details}</div>
            <div style="font-size:12px;color:#888;margin-top:2px;">{p.get('address', '')} / {station}</div>
            <div style="margin-top:6px;">
                <a href="{url}" style="font-size:12px;color:#2980b9;">詳細を見る ({source})</a>
            </div>
        </div>
        """

    cond_parts = []
    if "rent_max" in conditions:
        cond_parts.append(f"家賃≤{_format_rent(conditions['rent_max'])}")
    if "walk_max" in conditions:
        cond_parts.append(f"駅徒歩≤{conditions['walk_max']}分")
    if "size_min" in conditions:
        cond_parts.append(f"面積≥{conditions['size_min']}㎡")
    if "age_max" in conditions:
        cond_parts.append(f"築≤{conditions['age_max']}年")
    if conditions.get("layouts"):
        cond_parts.append(f"間取り: {', '.join(conditions['layouts'])}")
    cond_str = " / ".join(cond_parts) if cond_parts else "なし"

    truncated = f"<p style='color:#999;font-size:12px;'>他 {len(properties) - 30} 件...</p>" if len(properties) > 30 else ""

    return f"""
    <html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:600px;margin:0 auto;padding:16px;">
        <h2 style="color:#1a1a2e;font-size:16px;margin-bottom:16px;">
            🏠 新着 {len(properties)}件 — いい物件は7日まで
        </h2>
        {items_html}
        {truncated}
        <hr style="border:none;border-top:1px solid #eee;margin:16px 0;">
        <p style="font-size:12px;color:#999;">
            条件: {cond_str}<br>
            <a href="https://7days.actraise.org" style="color:#2980b9;">全物件を見る</a>
        </p>
    </body></html>
    """


def send_email(subject: str, html_body: str) -> bool:
    smtp_user = os.environ.get("NOTIFY_SMTP_USER", "")
    smtp_pass = os.environ.get("NOTIFY_SMTP_PASSWORD", "")
    to_raw = os.environ.get("NOTIFY_EMAIL_TO", "")

    if not smtp_user or not smtp_pass or not to_raw:
        logger.warning("[notifier] SMTP credentials or recipients not configured")
        return False

    to_list = [addr.strip() for addr in to_raw.split(",") if addr.strip()]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = ", ".join(to_list)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_list, msg.as_string())
        logger.info(f"[notifier] email sent to {to_list}")
        return True
    except Exception:
        logger.exception("[notifier] failed to send email")
        return False


async def notify_if_needed(conn: sqlite3.Connection, prev_fetch_at: str) -> int:
    """Check for new matching properties since ``prev_fetch_at`` and email if any.

    Returns the number of matching properties found (0 means no email sent).
    """
    if os.environ.get("NOTIFY_ENABLED") != "1":
        return 0

    cond = _load_conditions()
    matched = get_new_matching(conn, prev_fetch_at, cond)

    if not matched:
        logger.info(f"[notifier] no new matches since {prev_fetch_at}")
        return 0

    logger.info(f"[notifier] {len(matched)} new matches — sending email")
    subject = f"🏠 新着 {len(matched)}件 — いい物件は7日まで"
    html = build_email_html(matched, cond)
    send_email(subject, html)
    return len(matched)
