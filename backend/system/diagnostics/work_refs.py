"""Exact indexed lookups of Core-owned work metadata. No dispatch or app payload reads."""
from datetime import timezone
from sqlalchemy import and_, select

from backend.db.application_command import ApplicationCommandEpoch as Epoch, ApplicationCommandRequest as Request
from backend.db.application_task import ApplicationTaskRun as Task
from backend.db.device import DeviceCommand, DeviceEvent
from backend.system.diagnostics.catalog import MAX_CLOCK_SECONDS, WORK_ID, checked_work_record


def _queue_seconds(created, delivered, attempts):
    # Both are Core wall-clock observations. completed_at may originate on a
    # device with a different clock; deliberately never read or subtract it.
    if not attempts or created is None or delivered is None:
        return None
    def utc(value):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    elapsed = (utc(delivered) - utc(created)).total_seconds()
    return int(elapsed) if 0 <= elapsed <= MAX_CLOCK_SECONDS else None


def observe_work(db, installation, reference):
    if type(reference) is not str or not WORK_ID.fullmatch(reference):
        raise ValueError('Invalid work reference')
    observation = {'reference': reference, 'status': 'not_found_in_scope'}
    owner = (Task.installation_id == installation.id, Task.package_id == installation.module_package_id,
             Task.incarnation == installation.authority_incarnation)
    if reference.startswith('task_'):
        row = db.execute(select(Task.state, Task.progress, Task.dispatched, Task.started)
                         .where(Task.task_run_id == reference, *owner)).one_or_none()
        if row is not None:
            boundary = {(False, False): 'no_dispatch_record', (True, False): 'dispatch_recorded',
                        (True, True): 'start_permit_consumed', (False, True): 'inconsistent'}[row.dispatched,row.started]
            observation.update(status='found', recorded_state=row.state, progress=row.progress, start_boundary=boundary)
    else:
        # Current exact package + command epoch, invalidated at restore/lifecycle boundaries.
        # A reference from another owner/epoch and an unknown reference are indistinguishable.
        query = (select(DeviceCommand.status, DeviceCommand.created_at, DeviceCommand.delivered_at,
                        DeviceCommand.delivery_attempts, Request.claimed, Task.task_run_id, DeviceEvent.id.label('event_record'))
                 .select_from(Request)
                 .join(DeviceCommand, DeviceCommand.command_id == Request.command_id)
                 .join(Epoch, and_(Epoch.installation_id == Request.installation_id, Epoch.generation == Request.generation))
                 .outerjoin(Task, and_(Task.task_run_id == Request.task_run_id, *owner))
                 # The authorized sensor can be different from the command target.
                 # Use the relation saved by event admission, not a guessed device match.
                 .outerjoin(DeviceEvent, and_(DeviceEvent.event_id == Request.passage_event_id,
                                              DeviceEvent.producer_kind == 'device', DeviceEvent.device_id.is_not(None)))
                 .where(Request.command_id == reference, Request.installation_id == installation.id,
                        Request.package_id == installation.module_package_id))
        row = db.execute(query).one_or_none()
        if row is not None:
            observation.update(status='found', recorded_state=row.status, linked_task=row.task_run_id,
                               device_event_recorded=row.event_record is not None,
                               delivery={'recorded_attempts': row.delivery_attempts, 'permit_claimed': row.claimed,
                                         'queue_to_latest_offer_seconds': _queue_seconds(
                                             row.created_at, row.delivered_at, row.delivery_attempts)})
    try:
        return checked_work_record(observation)
    except ValueError:
        return {'reference': reference, 'status': 'unavailable'}
