"""Finite owner-VM interval/calendar exercise, imported by the unprivileged CLI."""
from datetime import UTC,datetime,timedelta
import json
import os
import time
import uuid


def run(args,client,state,parser):
    previous=json.loads(state.read_text()) if state.is_file() else None
    def observe(saved,cancel=False):
        if saved.get("kind")=="schedule":
            method=client.cancel_task_schedule if cancel else client.lookup_task_schedule
        else:method=client.cancel_task if cancel else client.lookup_task
        return method("calculate",request_id=saved["request_id"])
    if args.lookup or args.cancel:
        if previous is None or previous.get("kind")!="schedule":return None
        result=observe(previous,args.cancel);print(json.dumps(result),flush=True)
        if result["last_request_id"]:
            print(json.dumps(client.lookup_task("calculate",request_id=result["last_request_id"])),flush=True)
        return 0
    if previous and observe(previous)["status"] in {"queued","running","unknown","active","blocked"}:
        parser.error("Previous request is unresolved; use --lookup or --cancel")
    if not args.interval and not args.calendar:return None
    if not 1<=args.runs<=10 or args.interval is not None and not 5<=args.interval<=3600:
        parser.error("runs: 1..10; interval: 5..3600 seconds")
    now=datetime.now(UTC);start=now+timedelta(seconds=args.delay)
    if args.calendar:
        from zoneinfo import ZoneInfo
        from three_mm_platform_wire.task_time import next_occurrence
        local=now.astimezone(ZoneInfo(args.timezone))+timedelta(minutes=1)
        rule={"kind":"calendar","timezone":args.timezone,"hour":local.hour,"minute":local.minute}
        start=now;count=1
        due=next_occurrence({**rule,"weekdays":[0,1,2,3,4,5,6]},start,start+timedelta(days=2),now)
        if due is None or due>now+timedelta(seconds=120):parser.error("Next calendar time is outside this short VM exercise")
        end=due+timedelta(seconds=15)
    else:
        rule={"kind":"interval","every_seconds":args.interval};count=args.runs
        end=start+timedelta(seconds=(count-1)*args.interval+15)
    saved={"kind":"schedule","request_id":uuid.uuid4().hex,"upper":args.upper,"rule":rule,
        "start_at":start.isoformat(),"end_at":end.isoformat(),"max_occurrences":count}
    with state.open("w") as stream:
        json.dump(saved,stream);stream.flush();os.fsync(stream.fileno())
    descriptor=os.open(state.parent,os.O_RDONLY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)
    print("Schedule request:",saved["request_id"],flush=True)
    from three_mm_application_sdk import ApplicationPlatformError
    try:
        result=client.create_task_schedule("calculate",request_id=saved["request_id"],
            payload={"upper":args.upper,"pause_ms":800},rule=rule,start_at=start,end_at=end,max_occurrences=count)
    except ApplicationPlatformError:
        print("Admission reply unavailable. Request saved; use --lookup. Do not resubmit.",flush=True);return 2
    print("Admitted:",result["status"],flush=True)
    last=None;seen={};confirmed=set();limit=time.monotonic()+(end-now).total_seconds()+5
    while True:
        result=observe(saved);marker=json.dumps(result,sort_keys=True)
        if marker!=last:print(json.dumps(result),flush=True);last=marker
        key=result["last_request_id"]
        if key:
            child=client.lookup_task("calculate",request_id=key);current=(child["status"],child["progress"])
            if seen.get(key)!=current:print(json.dumps(child),flush=True);seen[key]=current
            if child["status"]=="succeeded" and key not in confirmed:
                expected=args.upper*(args.upper+1)//2;assert child["result"]=={"total":expected}
                print("PASS: total =",expected,flush=True);confirmed.add(key)
            elif child["status"] in {"unknown","failed","expired"}:return 2
        if result["status"] in {"cancelled","blocked"}:return 0 if result["status"]=="cancelled" else 2
        if result["status"]=="exhausted" and len(confirmed)>=count:
            print("PASS: schedule completed; confirmed occurrences =",len(confirmed),flush=True);return 0
        if time.monotonic()>=limit:
            print("Original request saved. Use --lookup.",flush=True);return 2
        time.sleep(.2)
