import sys

if sys.argv[1:] == ["--connector-execute"]:
    from three_mm_platform_runtime.connector_execute import main
else:
    from three_mm_platform_runtime.server import main

raise SystemExit(main())
