"""Email service — sends transactional emails via SMTP (password resets, etc.)"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def send_password_reset_email(
    app_config: dict, to_email: str, new_password: str, role: str
) -> bool:
    """Send a password-reset email containing the new plaintext password.

    Returns True on success, False on any failure (never raises).
    """
    host = app_config.get("MAIL_HOST", "smtp.gmail.com")
    port = app_config.get("MAIL_PORT", 587)
    username = app_config.get("MAIL_USERNAME", "")
    password = app_config.get("MAIL_PASSWORD", "")
    use_tls = app_config.get("MAIL_USE_TLS", True)
    from_addr = app_config.get("ADMIN_EMAIL", username)

    if not username or not password:
        logger.warning(
            "SMTP credentials not configured (MAIL_USERNAME / MAIL_PASSWORD empty) — cannot send email"
        )
        return False

    role_label = role.capitalize()
    subject = "FMI Codes 2026 — Your new password"

    plain_body = (
        f"Hi, 👋\n\n"
        f"📢 A password reset was requested for your {role_label} account at FMI Codes 2026.\n\n"
        f"Your new password is:  {new_password}\n"
        f"Please log in and change it as soon as possible.\n\n"
        f"⚠ If you did not request this, someone may have entered your email by mistake. ⚠\n\n"
        f"📍 Your previous password has been replaced — use the new one above to log in.\n"
        f" — FMI Codes Team 💻"
    )

    html_body = f"""\
<div style="font-family:'Inter',system-ui,sans-serif;max-width:540px;margin:0 auto;padding:36px 40px;
            background:#0b1021;color:#e2e8f0;border-radius:14px;border:1px solid rgba(255,255,255,0.07);">

  <!-- Header -->
  <div style="margin-bottom:28px;">
    <h1 style="margin:0 0 4px;font-size:22px;font-weight:700;color:#60a5fa;letter-spacing:-0.3px;">
      FMI Codes 2026
    </h1>
    <p style="margin:0;font-size:13px;color:#475569;text-transform:uppercase;letter-spacing:0.8px;">
      Password Reset
    </p>
  </div>

  <!-- Greeting -->
  <p style="font-size:20px;margin:0 0 20px;">Hi! 👋</p>

  <!-- Intro -->
  <p style="margin:0 0 24px;line-height:1.6;">
    📢 A password reset was requested for your
    <strong style="color:#93c5fd;">{role_label}</strong> account at FMI&nbsp;Codes&nbsp;2026.
  </p>

  <!-- Password box -->
  <p style="margin:0 0 8px;font-size:13px;color:#94a3b8;font-weight:500;">Your new password is:</p>
  <div style="margin:0 0 8px;padding:16px 20px;background:rgba(96,165,250,0.07);
              border:1px solid rgba(96,165,250,0.25);border-radius:10px;
              font-family:'Courier New',Courier,monospace;font-size:20px;
              letter-spacing:3px;text-align:center;color:#f0f6ff;word-break:break-all;">
    {new_password}
  </div>
  <p style="margin:0 0 28px;font-size:13px;color:#64748b;text-align:center;">
    Please <strong style="color:#e2e8f0;">log in</strong> and change it as soon as possible.
  </p>

  <!-- Warning -->
  <div style="padding:14px 18px;background:rgba(245,158,11,0.08);
              border:1px solid rgba(245,158,11,0.28);border-radius:10px;
              color:#fcd34d;font-size:13px;line-height:1.6;margin-bottom:20px;">
    ⚠&nbsp; If you did not request this, someone may have entered your email by mistake. &nbsp;⚠
  </div>

  <!-- Note -->
  <p style="margin:0 0 28px;font-size:13px;color:#94a3b8;line-height:1.6;">
    📍 Your previous password has been replaced&nbsp;&mdash; use the new one above to log in.
  </p>

  <!-- Footer -->
  <hr style="border:none;border-top:1px solid rgba(255,255,255,0.08);margin:0 0 20px;">
  <p style="margin:0;font-size:13px;color:#475569;">
    &mdash; FMI Codes Team 💻
  </p>

</div>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            if use_tls:
                server.starttls()
            server.login(username, password)
            server.sendmail(from_addr, [to_email], msg.as_string())
        logger.info("Password reset email sent to %s (role=%s)", to_email, role)
        return True
    except Exception as e:
        logger.error("Failed to send password reset email to %s: %s", to_email, e)
        return False
