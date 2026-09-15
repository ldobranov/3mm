"""Isolated Linux/Pi scheduler check; never invokes an extension or hardware.

Run from the checkout: python -m deployment.benchmark_application_jobs
Optional argv[1] is base64 scheduler source for testing against installed deps.
The SQLite database and all scheduler state are temporary.
"""
import base64
import json
import os
from pathlib import Path
import resource
import sys
import tempfile
import time
import types


def main():
    with tempfile.TemporaryDirectory(prefix='3mm-job-benchmark-') as temporary:
        os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(temporary) / 'state.db')
        import backend.database
        from sqlalchemy import Column, DateTime, Integer, String, create_engine
        from sqlalchemy.orm import sessionmaker
        from backend.db.base import Base
        from backend.db.module import ApplicationJobState as State, ApplicationExtensionInstallation as Installation, ModulePackage
        from backend.config import ApplicationRuntimeSettings
        # Compatibility only in this isolated process for pre-migration installations.
        for name, kind in [('lease_token', String(32)), ('lease_instance_id', String(24)),
                           ('lease_package_id', Integer()), ('last_scheduled_at', DateTime(timezone=True)),
                           ('last_duration_ms', Integer()), ('last_lateness_ms', Integer())]:
            if not hasattr(State, name):
                setattr(State, name, Column(kind, nullable=True))
        if len(sys.argv) > 1:
            jobs = types.ModuleType('isolated_application_jobs')
            sys.modules[jobs.__name__] = jobs
            exec(compile(base64.b64decode(sys.argv[1]), '<scheduler under test>', 'exec'), jobs.__dict__)
        else:
            from backend.services import application_jobs as jobs
        engine = create_engine(os.environ['DATABASE_URL'])
        Base.metadata.create_all(engine)
        sessions = sessionmaker(engine)
        with sessions() as db:
            for number in (1, 2):
                package = ModulePackage(module_id=f'org.example.benchmark{number}', version='1.0.0', manifest={},
                    sha256=str(number)*64, size_bytes=1, file_path='mock', registrations=[])
                db.add(package); db.flush()
                db.add(Installation(module_id=package.module_id, module_package_id=package.id,
                    instance_id=str(number)*24, active_version='1.0.0', status='active', enabled=True, socket_path='mock'))
            db.commit()
        job = types.SimpleNamespace(job_id='check', handler_operation_id='check', interval_seconds=5, catch_up='once')
        jobs.load_application_definition = lambda package: types.SimpleNamespace(jobs=[job])
        starts = []
        def invoke(app, *args, **kwargs):
            if app.instance_id == '1'*24:
                time.sleep(6)
            else:
                starts.append(time.monotonic())
            return {}
        jobs.invoke_application = invoke
        scheduler = jobs.ApplicationJobScheduler(ApplicationRuntimeSettings(), sessions)
        wall, cpu, ticks = time.monotonic(), time.process_time(), 0
        try:
            while time.monotonic() - wall < 16:
                delay = scheduler.tick()
                ticks += 1
                time.sleep(delay)
        finally:
            scheduler.close()
        elapsed = time.monotonic() - wall
        print(json.dumps({'wall_seconds': round(elapsed, 3), 'cpu_seconds': round(time.process_time()-cpu, 3),
            'cpu_one_core_percent': round(100*(time.process_time()-cpu)/elapsed, 2),
            'process_peak_rss_mib': round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024, 2),
            'scheduler_ticks': ticks, 'fast_job_starts': len(starts),
            'fast_job_gaps_seconds': [round(b-a, 3) for a,b in zip(starts, starts[1:])]}))
        engine.dispose()


if __name__ == '__main__':
    main()
