import os
import ray
import time
import asyncio
import logging
from fighthealthinsurance.fax_actor import FaxActor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@ray.remote(max_restarts=-1, max_task_retries=-1)
class FaxPollingActor:
    """
    Actor responsible for polling and triggering delayed fax sending in a loop.
    """

    def __init__(self, interval: int = 60):
        """
        Initializes the FaxPollingActor, creates an instance of FaxActor, 
        and sets up polling configurations.
        
        Args:
            interval (int): The time interval (in seconds) between polling cycles.
        """
        logger.info("Starting FaxPollingActor...")
        time.sleep(1)  # Small delay for setup

        self.fax_actor = FaxActor.options(name="fpa-worker", namespace="fhi").remote()
        self.interval = interval
        self.sent_count = 0
        self.error_count = 0
        self.actor_error_count = 0
        self.running = False

        logger.info(f"Created FaxActor instance: {self.fax_actor}")

    async def hello(self) -> str:
        """Health check endpoint for the actor."""
        return "Hi"

    async def run(self) -> bool:
        """
        Runs the polling process in a loop. It periodically checks for delayed faxes 
        and triggers the sending process via FaxActor.
        """
        logger.info("Starting fax polling loop...")
        self.running = True

        while self.running:
            await asyncio.sleep(1)  # Prevents high CPU usage
            try:
                logger.info("Checking for delayed remote faxes...")
                sent, failed = await self.fax_actor.send_delayed_faxes.remote()

                self.sent_count += sent
                self.error_count += failed

                logger.info(f"Sent {sent} faxes, {failed} failed in this run.")

            except Exception as e:
                logger.error(f"Error while checking outbound faxes: {e}")
                self.actor_error_count += 1

            logger.info(f"Waiting {self.interval} seconds for next polling cycle...")
            await asyncio.sleep(self.interval)

        logger.info("FaxPollingActor stopped.")
        return True

    async def stop(self):
        """Stops the polling loop."""
        logger.info("Stopping FaxPollingActor...")
        self.running = False

    async def count(self) -> int:
        """Returns the total count of successfully sent faxes."""
        return self.sent_count

    async def error_count(self) -> int:
        """Returns the total count of fax sending failures."""
        return self.error_count

    async def actor_error_count(self) -> int:
        """Returns the total count of actor-level errors."""
        return self.actor_error_count
