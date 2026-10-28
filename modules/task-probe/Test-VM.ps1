# Use the installed, pinned SDK and the application's unprivileged OS principal.
& wsl.exe -d Ubuntu-26.04 -u root -- /opt/3mm/current/.venv/bin/python /opt/3mm/current/modules/task-probe/vm_test.py @args
if ($LASTEXITCODE -ne 0) {
    throw "Task Probe returned exit code $LASTEXITCODE. Use --lookup to inspect a saved request."
}
