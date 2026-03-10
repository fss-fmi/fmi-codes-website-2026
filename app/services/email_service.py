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

    # TODO: Shmiti da opravi tva syobshtenie da e KVO friendly
    plain_body = (
        f"Hi,\n\n"
        f"A password reset was requested for your {role_label} account at FMI Codes 2026.\n\n"
        f"Your new password is:  {new_password}\n\n"
        f"Please log in and change it as soon as possible.\n\n"
        f"If you did not request this, someone may have entered your email by mistake. "
        f"Your previous password has been replaced — use the new one above to log in.\n\n"
        f"— FMI Codes Team"
    )

    html_body = f"""\
<div style="font-family:'Inter',system-ui,sans-serif;max-width:520px;margin:0 auto;padding:32px;
            background:#0b1021;color:#e2e8f0;border-radius:12px;">
  <h2 style="margin:0 0 8px;color:#60a5fa;">FMI Codes 2026</h2>
  <p style="color:#94a3b8;margin:0 0 24px;font-size:14px;">Password Reset</p>
  <p>A password reset was requested for your <strong>{role_label}</strong> account.</p>
  <div style="margin:20px 0;padding:16px;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);
              border-radius:8px;font-family:monospace;font-size:18px;letter-spacing:1px;text-align:center;">
    {new_password}
  </div>
  <p>Please <strong>log in</strong> and change your password as soon as possible.</p>
  <p style="color:#64748b;font-size:13px;margin-top:24px;">
    If you did not request this, someone may have entered your email by mistake.
    Your previous password has been replaced&nbsp;&mdash; use the new one above to log in.
  </p>
  <hr style="border:none;border-top:1px solid rgba(255,255,255,0.08);margin:24px 0;">
  <p style="color:#475569;font-size:12px;margin:0;">FMI Codes Team &bull; Sofia University</p>
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
