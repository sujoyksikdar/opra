from django.core import mail
from django.urls import reverse

def send_otp_email(request, user, code):
    subject = "Your OPRA verification code"
    verify_url = request.build_absolute_uri(
        reverse("appauth:verify_otp") + f"?uid={user.id}"
    )
    text = (
        f"Hi {user.username},\n\n"
        f"Your verification code is: {code}\n"
        f"This code expires in 10 minutes.\n\n"
        f"Verify here: {verify_url}\n\n"
        "— OPRA"
    )
    mail.send_mail(subject, text, "opra@cs.binghamton.edu", [user.email])
