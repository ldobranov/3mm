"""Mock capability acceptance using public SDK only; no business SQL or jobs."""

from three_mm_application_sdk import ApplicationContext, ApplicationMigration, OperationContext


def get_migrations():
    # The existing host still owns its compatibility schema journal. This
    # profile requests no scoped DB and creates no application business tables.
    return [ApplicationMigration("0001", lambda _connection: None)]


class ScopedReferenceService:
    def __init__(self, application: ApplicationContext):
        self.application = application

    def handle(self, operation_id, payload, context: OperationContext):
        if operation_id == "health":
            return {"status": "ready"}
        platform = self.application.platform
        if platform is None:
            raise RuntimeError("Public platform is unavailable")
        if operation_id == "probe":
            if not context.idempotency_key:
                raise ValueError("Preserve one request ID for the exact logical request")
            result = platform.submit_command("acceptance", request_id=context.idempotency_key,
                arguments=payload["arguments"], ttl_seconds=5)
            # Queued/expired/unknown is not proof of hardware execution.
            return {"request_id": context.idempotency_key, "status": result["status"]}
        if operation_id == "lookup":
            return platform.command_lookup(binding_id="acceptance", request_id=payload["request_id"])
        raise ValueError("Operation is unsupported")


def create_service(application: ApplicationContext):
    return ScopedReferenceService(application)
