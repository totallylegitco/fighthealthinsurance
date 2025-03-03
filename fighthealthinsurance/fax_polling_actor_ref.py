import threading
import time

import ray
from fighthealthinsurance.fax_polling_actor import FaxPollingActor


class FaxPollingActorRef:
    """A reference to the fax polling actor with proper handling of side effects and thread safety."""

    def __init__(self):
        # Use an instance variable for the actor reference
        self.fax_polling_actor = None
        # Add a lock to ensure thread-safe access to the actor reference
        self._lock = threading.Lock()

    def get(self):
        """
        Returns the fax polling actor. If it doesn't exist, create a new detached remote actor.
        Note: This method has side effects (actor creation and printing to the console).
        """
        name = "fax_polling_actor"
        # Ensure thread-safe check and creation of the actor
        with self._lock:
            if self.fax_polling_actor is None:
                self.fax_polling_actor = FaxPollingActor.options(  # type: ignore
                    name=name, lifetime="detached", namespace="fhi", get_if_exists=True
                ).remote()
        # Kick off the remote task
        rr = self.fax_polling_actor.run.remote()
        print(f"Remote run of fax actor {rr}")
        return (self.fax_polling_actor, rr)


fax_polling_actor_ref = FaxPollingActorRef()
actor, result = fax_polling_actor_ref.get()
