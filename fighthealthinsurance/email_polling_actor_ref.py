import time
import threading
import ray
from fighthealthinsurance.email_polling_actor import EmailPollingActor


class EmailPollingActorRef:
    """A reference to the email polling actor with proper handling of side effects and thread safety."""

    def __init__(self):
        self.email_polling_actor = None
        self._lock = threading.Lock()

    def get(self):
        """
        Returns the email polling actor. If it doesn't exist, create a new detached remote actor.
        Note: This method has side effects (actor creation and logging).
        """
        name = "email_polling_actor"
        with self._lock:
            if self.email_polling_actor is None:
                self.email_polling_actor = EmailPollingActor.options(  # type: ignore
                    name=name, lifetime="detached", namespace="fhi", get_if_exists=True
                ).remote()
        # Kick off the remote task
        rr = self.email_polling_actor.run.remote()
        print(f"Remote run of email actor {rr}")
        return (self.email_polling_actor, rr)


# Usage example
email_polling_actor_ref = EmailPollingActorRef()
