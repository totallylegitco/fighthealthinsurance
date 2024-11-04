import os

import ray
from fighthealthinsurance.fax_actor import FaxActor
import time


@ray.remote
class FaxPollingActor:
    def __init__(self):
        # This is seperate from the global one
        name = "fpa-worker"
        self.fax_actor = FaxActor.options(  # type: ignore
            name=name, namespace="fhi"
        ).remote()

    def run(self) -> bool:
        self.running = True
        while self.running:
            try:
                print(ray.get(self.fax_actor.send_delayed_faxes.remote()))
                time.sleep(60)
            except Exception as e:
                print(f"Error {e} while checking outbound faxes")
        return True
