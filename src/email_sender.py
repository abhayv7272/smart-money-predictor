import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import re
import base64

class EmailSender:
    def __init__(self, recipient_email="abhayv7272@gmail.com"):
        self.recipient_email = recipient_email
        self.smtp_server = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.environ.get("MAIL_PORT", 587))
        self.smtp_user = os.environ.get("MAIL_USERNAME", "")
        self.smtp_pass = os.environ.get("MAIL_PASSWORD", "")
        self.sender_email = os.environ.get("MAIL_FROM", self.smtp_user or "smart-money-bot@algorithmic.ai")

    def send_report(self, subject, html_content):
        if not self.smtp_user or not self.smtp_pass:
            msg="SMTP credentials are not configured; HTML report was saved locally."
            if os.environ.get("REQUIRE_EMAIL","").lower() in {"1","true","yes"}:
                raise RuntimeError(msg)
            print(f"[INFO] {msg}")
            print(f"[INFO] Report is ready for automated dispatch to: {self.recipient_email}")
            return False
            
        try:
            # Gmail commonly strips data-URI images. Convert generated signal charts into
            # inline CID attachments while keeping data URIs in the saved standalone HTML.
            images=[]
            pattern=re.compile(r'data:image/png;base64,([A-Za-z0-9+/=]+)')
            def replace_image(match):
                cid=f"signal_chart_{len(images)}"
                images.append((cid,base64.b64decode(match.group(1))))
                return f"cid:{cid}"
            email_html=pattern.sub(replace_image,html_content)

            msg = MIMEMultipart("related")
            msg["Subject"] = subject
            msg["From"] = f"Smart Money Intelligence <{self.sender_email}>"
            msg["To"] = self.recipient_email
            alternative=MIMEMultipart("alternative")
            alternative.attach(MIMEText(email_html,"html","utf-8"))
            msg.attach(alternative)
            for cid,payload in images:
                image=MIMEImage(payload,_subtype="png")
                image.add_header("Content-ID",f"<{cid}>")
                image.add_header("Content-Disposition","inline",filename=f"{cid}.png")
                msg.attach(image)
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_pass)
                server.sendmail(self.sender_email, self.recipient_email, msg.as_string())
                
            print(f"✅ Successfully dispatched daily report email to: {self.recipient_email}")
            return True
        except Exception as e:
            if os.environ.get("REQUIRE_EMAIL","").lower() in {"1","true","yes"}:
                raise RuntimeError(f"Email dispatch failed: {e}") from e
            print(f"⚠️ Email dispatch error: {e}")
            return False
