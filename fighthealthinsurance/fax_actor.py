import os
import time
import asyncio
import logging
from typing import Tuple
from datetime import timedelta
import ray
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.urls import reverse
from django.db import connection
from django.core.management import call_command
from fighthealthinsurance.models import FaxesToSend
from fighthealthinsurance.fax_utils import flexible_fax_magic

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@ray.remote(max_restarts=-1, max_task_retries=-1)
class FaxActor:
    """
    Actor responsible for managing fax operations, including sending faxes, 
    retrying failed transmissions, and managing database operations.
    """

    def __init__(self):
        """
        Initializes the actor, ensuring Django's application settings are properly configured.
        """
        time.sleep(1)  # Artificial delay to ensure environment setup
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fighthealthinsurance.settings")

        from configurations.wsgi import get_wsgi_application
        get_wsgi_application()

        logger.info("FaxActor initialized successfully.")

    def hi(self) -> str:
        """Simple health check for the actor."""
        return "ok"

    def db_settings(self) -> str:
        """Returns database connection settings as a string."""
        return str(dict(connection.settings_dict))

    def version(self) -> int:
        """Returns the current version of the actor."""
        return 1  # Increment this value to restart the actor

    def test_create_fax_object(self, **kwargs) -> FaxesToSend:
        """Creates a fax object for testing purposes."""
        fax = FaxesToSend.objects.create(**kwargs)
        
        if "date" in kwargs:
            fax.date = kwargs["date"]
            fax.save()

        return fax

    def test_delete(self, fax: FaxesToSend) -> Tuple[int, dict]:
        """Deletes a fax object."""
        return fax.delete()

    def test_migrate(self):
        """Runs migrations in test environments."""
        env = os.getenv("DJANGO_CONFIGURATION")
        if env not in {"Test", "TestActor", "TestSync"}:
            raise Exception(f"Attempted to run test migrations in a non-test environment: {env}")

        try:
            FaxesToSend.objects.all().delete()
            logger.info("Deleted all faxes in test environment.")
        except Exception as e:
            logger.warning(f"Couldn't delete faxes: {e}")
            call_command("migrate")

    def send_delayed_faxes(self) -> Tuple[int, int]:
        """
        Sends faxes that are marked as `should_send=True` but haven't been sent yet,
        and are older than an hour.

        Returns:
            Tuple[int, int]: Number of faxes successfully sent, and number of failures.
        """
        target_time = timezone.now() - timedelta(hours=1)
        delayed_faxes = FaxesToSend.objects.filter(should_send=True, sent=False, date__lt=target_time)

        success_count = 0
        failure_count = 0

        logger.info(f"Sending faxes older than {target_time}...")

        for fax in delayed_faxes:
            try:
                logger.info(f"Attempting to send fax {fax.uuid}")
                success_count += 1
                response = self.do_send_fax_object(fax)
                logger.info(f"Successfully sent fax {fax.uuid}, response: {response}")
            except Exception as e:
                logger.error(f"Error sending fax {fax.uuid}: {e}")
                failure_count += 1

        return success_count, failure_count

    def do_send_fax(self, hashed_email: str, uuid: str) -> bool:
        """
        Sends a fax by looking it up in the database.

        Args:
            hashed_email (str): Hashed email identifier.
            uuid (str): Unique identifier of the fax.

        Returns:
            bool: Whether the fax was successfully sent.
        """
        try:
            fax = FaxesToSend.objects.get(uuid=uuid, hashed_email=hashed_email)
            return self.do_send_fax_object(fax)
        except FaxesToSend.DoesNotExist:
            logger.error(f"Fax with UUID {uuid} and email hash {hashed_email} not found.")
            return False

    def _update_fax_for_sending(self, fax: FaxesToSend):
        """Marks a fax as being attempted for sending."""
        fax.attempting_to_send_as_of = timezone.now()
        fax.save()

    def _update_fax_for_sent(self, fax: FaxesToSend, success: bool):
        """Marks a fax as successfully sent or failed."""
        fax.sent = True
        fax.fax_success = success
        fax.save()
        logger.info(f"Fax {fax.uuid} marked as {'sent' if success else 'failed'}.")

    def do_send_fax_object(self, fax: FaxesToSend) -> bool:
        """
        Handles the actual fax sending logic.

        Args:
            fax (FaxesToSend): Fax object to be sent.

        Returns:
            bool: Whether the fax was successfully sent.
        """
        if not fax.denial_id or not fax.destination:
            logger.warning(f"Fax {fax.uuid} is missing required data (denial_id/destination). Skipping.")
            return False

        extra_info = []
        if fax.denial_id.claim_id and len(fax.denial_id.claim_id) > 2:
            extra_info.append(f"This is regarding claim ID {fax.denial_id.claim_id}.")
        if fax.name and len(fax.name) > 2:
            extra_info.append(f"This fax is sent on behalf of {fax.name}.")

        self._update_fax_for_sending(fax)
        logger.info(f"Sending fax {fax.uuid} to {fax.destination}.")

        fax_sent = False
        try:
            fax_sent = asyncio.run(
                flexible_fax_magic.send_fax(
                    input_paths=[fax.get_temporary_document_path()],
                    extra=" ".join(extra_info),
                    destination=fax.destination,
                    blocking=True,
                )
            )
        except Exception as e:
            logger.error(f"Error sending fax {fax.uuid}: {e}")

        self._update_fax_for_sent(fax, fax_sent)
        self._notify_user_of_fax_result(fax, fax_sent)

        return fax_sent

    def _notify_user_of_fax_result(self, fax: FaxesToSend, success: bool):
        """
        Sends an email notification to the user with the result of the fax transmission.

        Args:
            fax (FaxesToSend): Fax object.
            success (bool): Whether the fax was successfully sent.
        """
        fax_redo_link = f"https://www.fighthealthinsurance.com{reverse('fax-followup', kwargs={'hashed_email': fax.hashed_email, 'uuid': fax.uuid})}"
        context = {"name": fax.name, "success": success, "fax_redo_link": fax_redo_link}

        text_content = render_to_string("emails/fax_followup.txt", context)
        html_content = render_to_string("emails/fax_followup.html", context)

        msg = EmailMultiAlternatives(
            "Fax Transmission Status - Fight Health Insurance",
            text_content,
            "support42@fighthealthinsurance.com",
            [fax.email],
        )
        msg.attach_alternative(html_content, "text/html")

        try:
            msg.send()
            logger.info(f"Email sent to {fax.email} regarding fax {fax.uuid}.")
        except Exception as e:
            logger.error(f"Error sending email notification for fax {fax.uuid}: {e}")
