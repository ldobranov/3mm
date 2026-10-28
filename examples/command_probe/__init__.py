"""Minimal SDK consumer: no provider names, device IDs or Core imports.

The host supplies ApplicationContext.platform. Persist request_id before submit;
after a lost response use lookup(), never manufacture a replacement request.
"""

from three_mm_application_sdk import ApplicationPlatformClient


class CommandProbe:
    def __init__(self, platform: ApplicationPlatformClient, binding_id: str):
        self.platform = platform
        self.binding_id = binding_id

    def observe(self):
        return self.platform.discover_command(self.binding_id)

    def submit(self, *, request_id, arguments, ttl_seconds=5):
        observation = self.observe()
        candidates = observation["candidates"]
        if (observation["access"] != "granted" or len(candidates) != 1
                or not candidates[0]["selectable"] or candidates[0]["readiness"] != "ready"):
            return {"status": "not_submitted", "observation": observation}
        # Observation is advisory: Core still rechecks authority at submission
        # and again before the provider is permitted to attempt the effect.
        return self.platform.submit_command(self.binding_id, request_id=request_id,
            arguments=arguments, ttl_seconds=ttl_seconds)

    def lookup(self, request_id):
        return self.platform.command_lookup(binding_id=self.binding_id, request_id=request_id)
