import ray
import time
import asyncio

from functools import cached_property

from fighthealthinsurance.email_polling_actor import *
from fighthealthinsurance.ray import *


class EmailPollingActorRef:
    @cached_property
    def get(self):
        # Shut down existing actor
        try:
            a = ray.get_actor(name, namespace="fhi")
            if a is not None:
                ray.kill(a)
                time.sleep(10)
        except Exception as e:
            print(f"No exisitng email actor to stop {e}")

        email_polling_actor = EmailPollingActor.options(
            name=name, lifetime="detached", namespace="fhi"
        ).remote()
        # Kick of the remote task
        email_polling_actor.run.remote()
        return email_polling_actor


email_polling_actor_ref = EmailPollingActorRef()