"""Neutral public-SDK consumer; caller persists request IDs before schedule()."""
class TaskProbe:
    def __init__(self, platform):
        self.platform = platform

    def schedule(self, *, request_id, upper, pause_ms, due_at, not_after):
        return self.platform.submit_task("calculate", request_id=request_id,
            payload={"upper": upper, "pause_ms": pause_ms}, due_at=due_at, not_after=not_after)

    def lookup(self, request_id):
        return self.platform.lookup_task("calculate", request_id=request_id)
