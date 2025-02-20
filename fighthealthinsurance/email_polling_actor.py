import os
import ray
import time
import asyncio
import logging

from asgiref.sync import sync_to_async
from configurations.wsgi import get_wsgi_application
from fighthealthinsurance.followup_emails import ThankyouEmailSender, FollowUpEmailSender

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

name = "EmailPollingActor"

@ray.remote(max_restarts=-1, max_task_retries=-1)
class EmailPollingActor:
    """
    Actor responsible for polling and sending follow-up and thank-you emails asynchronously.
    """

    def __init__(self):
        """Initializes the EmailPollingActor, ensuring the Django app is properly configured."""
        logger.info("Initializing EmailPollingActor...")

        time.sleep(1)  # Small delay to ensure proper setup
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fighthealthinsurance.settings")
        get_wsgi_application()
        logger.info("Django WSGI application started.")

        # Initialize email senders
        self.followup_sender = FollowUpEmailSender()
        self.thankyou_sender = ThankyouEmailSender()
        self.running = False

        logger.info("Email senders initialized successfully.")

    async def run(self) -> None:
        """
        Starts polling for follow-up and thank-you email candidates.
        This function continuously checks for candidates and sleeps in between.
        """
        logger.info("Email polling started.")
        self.running = True

        while self.running:
            try:
                followup_candidates = await sync_to_async(self.followup_sender.find_candidates)()
                logger.info(f"Top follow-up candidates: {followup_candidates[:4]}")

                thankyou_candidates = await sync_to_async(self.thankyou_sender.find_candidates)()
                logger.info(f"Top thank-you candidates: {thankyou_candidates[:4]}")

                await asyncio.sleep(10)  # Polling interval
            except Exception as e:
                logger.error(f"Error encountered while checking messages: {e}")

        logger.info("Email polling stopped.")

    def stop(self):
        """Stops the polling loop."""
        logger.info("Stopping EmailPollingActor...")
        self.running = False
