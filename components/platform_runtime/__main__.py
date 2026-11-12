import sys

if sys.argv[1:] == ["--connector-execute"]:
    from components.platform_runtime.connector_execute import main
else:
    from components.platform_runtime.server import main

raise SystemExit(main())
