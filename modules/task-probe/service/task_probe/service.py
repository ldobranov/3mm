"""Bounded arithmetic result; local attempt journal demonstrates no replay."""
import time
import hashlib
from three_mm_application_sdk import ApplicationPlatformError


class Service:
    def __init__(self, application):
        self.application = application

    def handle(self, operation_id, payload, context):
        if operation_id == "health" and context.audience == "internal":
            return {"status": "ready"}
        if operation_id not in {"calculate","switch_output"} or context.audience != "internal" or context.task_execution is None:
            raise ValueError("The bounded handler requires its task execution context")
        task = context.task_execution
        with self.application.storage.transaction() as connection:
            connection.execute("INSERT INTO task_probe_attempts(task_run_id) VALUES (?)", (task.task_run_id,))
        self.application.platform.task_progress(task, 50)
        if operation_id=="switch_output":
            key=hashlib.sha256((task.task_run_id+":output").encode()).hexdigest()
            try:
                self.application.platform.submit_task_command(task,"output",request_id=key,
                    arguments={"channel":"gpio.output.1","value":payload["value"]},ttl_seconds=5)
            except ApplicationPlatformError:
                # The original identity is deterministic and journalled before
                # send; only observe after losing an admission reply.
                pass
            deadline=time.monotonic()+4
            while time.monotonic()<deadline:
                observed=self.application.platform.lookup_task_command(task.task_run_id,"output",request_id=key)
                if observed["status"]=="found":
                    command=observed["command"]
                    if command["status"]=="succeeded":
                        return {"command_id":command["command_id"],"request_id":key,"value":payload["value"]}
                    if command["status"] not in {"queued","delivered"}:
                        break
                time.sleep(.05)
            raise ValueError("Original task command outcome is not confirmed")
        time.sleep(payload["pause_ms"] / 1000)
        upper = payload["upper"]
        return {"total": upper * (upper + 1) // 2}


def create_service(application):
    return Service(application)
