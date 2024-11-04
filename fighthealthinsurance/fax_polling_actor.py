import os

import ray
from fighthealthinsurance.fax_actor import FaxActor
import time


@ray.remote
class FaxPollingActor:
    def __init__(self, i = 60):
        # This is seperate from the global one
        name = "fpa-worker"
        self.fax_actor = FaxActor.options(  # type: ignore
            name=name, namespace="fhi"
        ).remote()
        self.interval = i
        self.c = 0
        self.e = 0

    async def run(self) -> bool:
        self.running = True
        while self.running:
            try:
                (c, f) = ray.get(self.fax_actor.send_delayed_faxes.remote())
                self.e += f
                self.c += c
                time.sleep(self.interval)
            except Exception as e:
                print(f"Error {e} while checking outbound faxes")
                self.e = self.e + 1
        return True

    async def count(self) -> int:
        return self.c

    async def error_count(self) -> int:
        return self.e
