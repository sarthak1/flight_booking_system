import sendgrid
from sendgrid.helpers.mail import Mail
from app.core.settings import settings

sg = sendgrid.SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)

def send_confirmation(to_email: str, subject: str, html_content: str):
    message = Mail(
        from_email=(settings.FROM_EMAIL, settings.FROM_NAME),
        to_emails=to_email,
        subject=subject,
        html_content=html_content,
    )
    response = sg.send(message)
    return response.status_code
