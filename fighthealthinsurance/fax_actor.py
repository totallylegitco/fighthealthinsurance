from typing import Tuple
import ray
from fighthealthinsurance.fax_utils import *
from datetime import timedelta
import time
import asyncio

from django.core.mail import EmailMultiAlternatives, BadHeaderError
from django.template.loader import render_to_string
from django.utils import timezone
from django.urls import reverse
import logging
from smtplib import SMTPException
from django.core.exceptions import ValidationError, ImproperlyConfigured
from loguru import logger


@ray.remote(max_restarts=-1, max_task_retries=-1)
class FaxActor:
    def __init__(self):
        time.sleep(1)
        # This is a bit of a hack but we do this so we have the app configured
        from configurations.wsgi import get_wsgi_application

        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fighthealthinsurance.settings")
        get_wsgi_application()
        from fighthealthinsurance.models import FaxesToSend

    def hi(self):
        return "ok"

    def db_settings(self):
        from django.db import connection

        return str(dict(connection.settings_dict))

    def version(self):
        """Bump this to restart the fax actor."""
        return 1

    def _require_test_env(self):
        """Call this at the start of test only functions."""
        env = os.getenv("DJANGO_CONFIGURATION")
        if env not in ["Test", "TestActor", "TestSync"]:
            raise Exception(f"Tried to call test migrate in non-test env -- {env}")

    def test_create_fax_object(self, **kwargs):
        from fighthealthinsurance.models import FaxesToSend

        self._require_test_env()

        fax = FaxesToSend.objects.create(**kwargs)
        # reset the date to the specified old date for testing.
        if "date" in kwargs:
            fax.date = kwargs["date"]
            fax.save()
        return fax

    def test_delete(self, fax):
        self._require_test_env()
        return fax.delete()

    def test_migrate(self):
        from fighthealthinsurance.models import FaxesToSend
        from django.core.management import call_command

        self._require_test_env()

        try:
            FaxesToSend.objects.all().delete()
        except Exception as e:
            print(f"Couldn't delete faxes {e}")
            call_command("migrate")

    def send_delayed_faxes(self) -> Tuple[int, int]:
        from fighthealthinsurance.models import FaxesToSend

        target_time = timezone.now() - timedelta(hours=1)
        print(f"Sending faxes older than target: {target_time}")

        delayed_faxes = FaxesToSend.objects.filter(
            should_send=True, sent=False, date__lt=target_time
        )
        t = 0
        f = 0
        for fax in delayed_faxes:
            try:
                print(f"Attempting to send fax {fax}")
                t = t + 1
                response = self.do_send_fax_object(fax)
                print(f"Sent fax {fax} with result {response}")
            except Exception as e:
                print(f"Error sending fax {fax}: {e}")
                f = f + 1
        return (t, f)

    def do_send_fax(self, hashed_email: str, uuid: str) -> bool:
        # Now that we have an app instance we can import faxes to send
        from fighthealthinsurance.models import FaxesToSend

        fax = FaxesToSend.objects.filter(uuid=uuid, hashed_email=hashed_email).get()
        return self.do_send_fax_object(fax)

    def _update_fax_for_sending(self, fax):
        print(f"Recording attempt to send time")
        fax.attempting_to_send_as_of = timezone.now()
        fax.save()

    def _update_fax_for_sent(self, fax, fax_success):
        print(f"Fax send command returned :)")
        fax.sent = True
        fax.fax_success = fax_success
        fax.save()

    def do_send_fax_object(self, fax) -> bool:
        """Send a fax and notify the user via email with robust error handling."""
        try:
            email = fax.email
            denial = fax.denial_id

            # Validate fax details before sending
            if not denial or not fax.destination:
                logger.warning(f"Fax {fax.id} has missing denial or destination. Aborting.")
                return False

            # Construct extra message details
            extra = []
            if denial.claim_id and len(denial.claim_id) > 2:
                extra.append(f"This is regarding claim ID {denial.claim_id}.")
            if fax.name and len(fax.name) > 2:
                extra.append(f"This fax is sent on behalf of {fax.name}.")
            extra_message = " ".join(extra)

            self._update_fax_for_sending(fax)
            logger.info(f"Starting fax sending process for fax ID {fax.id}")

            # Run async function properly in a sync environment
            try:
                fax_sent = asyncio.run(
                    flexible_fax_magic.send_fax(
                        input_paths=[fax.get_temporary_document_path()],
                        extra=extra_message,
                        destination=fax.destination,
                        blocking=True,
                    )
                )
            except Exception as e:
                logger.error(f"Error sending fax {fax.id}: {e}", exc_info=True)
                fax_sent = False

            self._update_fax_for_sent(fax, fax_sent)
            logger.info(f"Fax sending completed for fax ID {fax.id}. Result: {fax_sent}")

            # Construct follow-up email
            fax_redo_link = f"https://www.fighthealthinsurance.com{reverse('fax-followup', kwargs={'hashed_email': fax.hashed_email, 'uuid': fax.uuid})}"
            context = {
                "name": fax.name,
                "success": fax_sent,
                "fax_redo_link": fax_redo_link,
            }

            email_sent = self.send_fax_followup_email(email, context)
            if email_sent:
                logger.info(f"Follow-up email successfully sent to {email}.")
            else:
                logger.error(f"Failed to send follow-up email to {email}.")

            return fax_sent

        except Exception as e:
            logger.error(f"Unexpected error in do_send_fax_object: {e}", exc_info=True)
            return False

    def send_fax_followup_email(self, to_email: str, context: dict) -> bool:
        """Send a follow-up email after fax sending."""
        try:
            if not to_email:
                raise ValidationError("Recipient email is required.")

            # Render email content
            text_content = render_to_string("emails/fax_followup.txt", context=context).strip()
            html_content = render_to_string("emails/fax_followup.html", context=context).strip()

            if not text_content and not html_content:
                raise ValidationError("Both text and HTML templates are empty.")

            msg = EmailMultiAlternatives(
                "Following up from Fight Health Insurance",
                text_content,
                "support42@fighthealthinsurance.com",
                [to_email],
            )

            if html_content:
                msg.attach_alternative(html_content, "text/html")

            msg.send()
            return True  # Email sent successfully

        except (BadHeaderError, SMTPException, ImproperlyConfigured, ValidationError) as e:
            logger.error(f"Email sending failed for {to_email}: {e}", exc_info=True)
            return False

        except Exception as e:
            logger.error(f"Unexpected error in send_fax_followup_email: {e}", exc_info=True)
            return False

