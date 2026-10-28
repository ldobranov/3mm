"""Real IANA clock transitions, strict schedule contracts and bounded arithmetic."""
from datetime import UTC, datetime, timedelta
import pytest
from three_mm_platform_wire.task_time import latest_occurrence, next_occurrence, occurrence_count
from three_mm_protocol.application_tasks import TaskScheduleCreateV1


def calendar(**changes):
    return {"kind": "calendar", "timezone": "Europe/Sofia", "hour": 3, "minute": 30,
        "weekdays": [6], "gap": "skip", "fold": "earliest", "misfire": "skip", **changes}


def test_spring_gap_skips_local_time_instead_of_moving_a_business_deadline():
    start=datetime(2026,3,23,tzinfo=UTC);end=start+timedelta(days=20)
    assert latest_occurrence(calendar(),start,end,datetime(2026,3,29,6,tzinfo=UTC)) is None
    assert next_occurrence(calendar(),start,end,start)==datetime(2026,4,5,0,30,tzinfo=UTC)


def test_autumn_fold_has_one_earliest_occurrence_even_during_the_second_hour():
    start=datetime(2026,10,20,tzinfo=UTC);end=start+timedelta(days=20)
    early=datetime(2026,10,25,0,30,tzinfo=UTC)
    assert latest_occurrence(calendar(),start,end,datetime(2026,10,25,1,45,tzinfo=UTC))==early
    assert next_occurrence(calendar(),start,end,early)==datetime(2026,11,1,1,30,tzinfo=UTC)
    assert occurrence_count(calendar(),start,None,datetime(2026,10,25,1,45,tzinfo=UTC))==1


def test_half_hour_gap_and_skipped_civil_date_are_also_skipped():
    start=datetime(2026,10,1,tzinfo=UTC);end=start+timedelta(days=20)
    rule=calendar(timezone="Australia/Lord_Howe",hour=2,minute=15)
    assert next_occurrence(rule,start,end,start)==datetime(2026,10,10,15,15,tzinfo=UTC)
    start=datetime(2011,12,29,tzinfo=UTC);end=start+timedelta(days=20)
    rule=calendar(timezone="Pacific/Apia",hour=12,minute=0,weekdays=[4])
    assert next_occurrence(rule,start,end,start)==datetime(2012,1,5,22,tzinfo=UTC)


def test_interval_is_utc_anchored_and_calendar_boundaries_are_end_exclusive():
    start=datetime(2026,10,25,0,30,tzinfo=UTC);end=start+timedelta(hours=3)
    rule={"kind":"interval","every_seconds":3600,"misfire":"skip"}
    assert latest_occurrence(rule,start,end,start+timedelta(hours=9))==start+timedelta(hours=2)
    assert occurrence_count(rule,start,None,start+timedelta(hours=2))==3
    assert next_occurrence(rule,start,end,start+timedelta(hours=2)) is None
    assert latest_occurrence(rule,start,end,start-timedelta(microseconds=1)) is None


@pytest.mark.parametrize("change",[
    {"rule":calendar(timezone="Missing/Zone")}, {"rule":calendar(fold="both")},
    {"rule":calendar(misfire="catch_up")}, {"rule":calendar(weekdays=[6,6])},
    {"rule":calendar(weekdays=[True])}, {"rule":{"kind":"interval","every_seconds":True}},
    {"rule":{"kind":"interval","every_seconds":1}}, {"history_limit":65},
    {"start_window_seconds":21}, {"payload":{"nested":{}}},
])
def test_public_schedule_contract_rejects_unbounded_or_ambiguous_policy(change):
    start=datetime.now(UTC)
    body={"task_id":"calculate","request_id":"a"*32,"payload":{"upper":100},
        "start_at":start,"end_at":start+timedelta(days=10),"rule":calendar(),**change}
    with pytest.raises(ValueError):TaskScheduleCreateV1.model_validate(body)
