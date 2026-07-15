"""Email service — sends transactional emails via SMTP (password resets, etc.)"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def send_password_reset_link_email(
    app_config: dict, to_email: str, reset_url: str, role: str
) -> bool:
    """C4: Send a password-reset email containing ONLY a secure reset link.

    The plaintext password is never included.  The link expires in 1 hour.
    Returns True on success, False on any failure (never raises).
    """
    host = app_config.get("MAIL_HOST", "smtp.gmail.com")
    port = app_config.get("MAIL_PORT", 587)
    username = app_config.get("MAIL_USERNAME", "")
    password = app_config.get("MAIL_PASSWORD", "")
    use_tls = app_config.get("MAIL_USE_TLS", True)
    from_addr = app_config.get("ADMIN_EMAIL", username)

    if not username or not password:
        logger.warning("SMTP credentials not configured — cannot send password reset link email")
        return False

    role_label = role.capitalize()
    subject = "FMI Codes 2026 — Reset your password"

    plain_body = (
        f"Hi,\n\n"
        f"A password reset was requested for your {role_label} account at FMI Codes 2026.\n\n"
        f"Click the link below to set a new password (valid for 1 hour):\n\n"
        f"  {reset_url}\n\n"
        f"If you did not request this, you can safely ignore this email.\n\n"
        f"— FMI Codes Team"
    )

    html_body = f"""\
<div style="font-family:'Inter',system-ui,sans-serif;max-width:540px;margin:0 auto;padding:36px 40px;
            background:#0b1021;color:#e2e8f0;border-radius:14px;border:1px solid rgba(255,255,255,0.07);">
  <div style="margin-bottom:28px;">
    <h1 style="margin:0 0 4px;font-size:22px;font-weight:700;color:#60a5fa;">FMI Codes 2026</h1>
    <p style="margin:0;font-size:13px;color:#475569;text-transform:uppercase;letter-spacing:0.8px;">
      Password Reset
    </p>
  </div>
  <p style="margin:0 0 20px;line-height:1.6;">
    A password reset was requested for your
    <strong style="color:#93c5fd;">{role_label}</strong> account.
    Click the button below to set a new password. The link is valid for <strong>1 hour</strong>.
  </p>
  <div style="text-align:center;margin:0 0 28px;">
    <a href="{reset_url}"
       style="display:inline-block;padding:14px 32px;background:#3b82f6;color:#fff;
              font-weight:600;font-size:15px;border-radius:8px;text-decoration:none;">
      Reset my password
    </a>
  </div>
  <p style="margin:0 0 28px;font-size:13px;color:#64748b;text-align:center;">
    Or copy and paste this URL into your browser:<br>
    <span style="color:#93c5fd;word-break:break-all;">{reset_url}</span>
  </p>
  <div style="padding:14px 18px;background:rgba(245,158,11,0.08);
              border:1px solid rgba(245,158,11,0.28);border-radius:10px;
              color:#fcd34d;font-size:13px;line-height:1.6;margin-bottom:20px;">
    If you did not request this, you can safely ignore this email.
    Your password has <strong>not</strong> been changed.
  </div>
  <hr style="border:none;border-top:1px solid rgba(255,255,255,0.08);margin:0 0 20px;">
  <p style="margin:0;font-size:13px;color:#475569;">— FMI Codes Team 💻</p>
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
        logger.info("Password reset link email sent (role=%s)", role)
        return True
    except Exception as e:
        logger.error("Failed to send password reset link email: %s", e)
        return False


def send_join_request_notification(
    app_config: dict,
    captain_email: str,
    captain_first_name: str,
    team_name: str,
    applicant_first_name: str,
    applicant_last_name: str,
) -> bool:
    """Notify a team captain that a new participant has requested to join their team.

    Returns True on success, False on any failure (never raises).
    """
    host = app_config.get("MAIL_HOST", "smtp.gmail.com")
    port = app_config.get("MAIL_PORT", 587)
    username = app_config.get("MAIL_USERNAME", "")
    password = app_config.get("MAIL_PASSWORD", "")
    use_tls = app_config.get("MAIL_USE_TLS", True)
    from_addr = app_config.get("ADMIN_EMAIL", username)

    if not username or not password:
        logger.warning("SMTP credentials not configured — cannot send join request notification")
        return False

    applicant_full = f"{applicant_first_name} {applicant_last_name}"
    subject = f"FMI Codes 2026 — New join request for {team_name}"

    plain_body = (
        f"Hi {captain_first_name}! 👋\n\n"
        f"📢 A new participant has requested to join your team at FMI Codes 2026.\n\n"
        f"Team:       {team_name}\n"
        f"Applicant:  {applicant_full}\n\n"
        f"Head over to your team dashboard to review and accept or decline the request.\n\n"
        f"📍 You can manage all pending requests from your team page.\n"
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
      Team Join Request
    </p>
  </div>

  <!-- Greeting -->
  <p style="font-size:20px;margin:0 0 20px;">Hi {captain_first_name}! 👋</p>

  <!-- Intro -->
  <p style="margin:0 0 24px;line-height:1.6;">
    📢 A new participant has requested to join your team at FMI&nbsp;Codes&nbsp;2026.
  </p>

  <!-- Details box -->
  <div style="margin:0 0 28px;padding:20px 24px;background:rgba(96,165,250,0.07);
              border:1px solid rgba(96,165,250,0.25);border-radius:10px;">
    <table style="width:100%;border-collapse:collapse;font-size:14px;">
      <tr>
        <td style="padding:6px 0;color:#94a3b8;font-weight:600;width:110px;">Team</td>
        <td style="padding:6px 0;color:#f0f6ff;font-weight:700;">{team_name}</td>
      </tr>
      <tr>
        <td style="padding:6px 0;color:#94a3b8;font-weight:600;">Applicant</td>
        <td style="padding:6px 0;color:#f0f6ff;font-weight:700;">{applicant_full}</td>
      </tr>
    </table>
  </div>

  <!-- CTA -->
  <p style="margin:0 0 28px;line-height:1.6;color:#cbd5e1;">
    Head over to your <strong style="color:#e2e8f0;">team dashboard</strong> to review and
    accept or decline the request.
  </p>

  <!-- Note -->
  <div style="padding:14px 18px;background:rgba(167,139,250,0.08);
              border:1px solid rgba(167,139,250,0.28);border-radius:10px;
              color:#c4b5fd;font-size:13px;line-height:1.6;margin-bottom:20px;">
    📍 You can manage all pending requests from your team page.
  </div>

  <!-- Footer -->
  <hr style="border:none;border-top:1px solid rgba(255,255,255,0.08);margin:0 0 20px;">
  <p style="margin:0;font-size:13px;color:#475569;">
    &mdash; FMI Codes Team 💻
  </p>

</div>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = captain_email
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            if use_tls:
                server.starttls()
            server.login(username, password)
            server.sendmail(from_addr, [captain_email], msg.as_string())
        logger.info("Join request notification sent (team=%s)", team_name)
        return True
    except Exception as e:
        logger.error("Failed to send join request notification: %s", e)
        return False
