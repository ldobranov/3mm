"""Safe offline format for a short Core database observation. No runtime imports."""

SOURCE_PREFIXES = (
    ("backend.accounts.", "accounts"),
    ("backend.applications.tasks.", "application_tasks"),
    ("backend.applications.events.", "application_events"),
    ("backend.applications.commands.", "application_commands"),
    ("backend.applications.", "applications"),
    ("backend.devices.", "devices"),
    ("backend.installation.", "installation"),
    ("backend.artifacts.", "packages"),
    ("backend.system.", "system"),
)
FAMILIES = frozenset(group for _, group in SOURCE_PREFIXES) | {"other"}


def checked_sample(value):
    """Project untrusted exported JSON onto fixed labels and bounded counters only."""
    def integer(number, low, high):
        return type(number) is int and low <= number <= high

    if (type(value) is not dict or not integer(value.get("schema_version"), 1, 1)
        or value.get("kind") != "sqlite_write_sample"
        or value.get("coverage") != "new_core_engine_connections"
        or not integer(value.get("window_ms"), 0, 2**53 - 1)
        or type(value.get("limited")) is not bool or type(value.get("families")) is not list
        or len(value["families"]) > len(FAMILIES)):
        raise ValueError("Invalid database write sample")
    rows, seen, pending = [], set(), 0
    for row in value["families"]:
        if type(row) is not dict:
            raise ValueError("Invalid database observation")
        name, count, duration, opened = (row.get(k) for k in ("source", "observed", "longest_ms", "open_at_end"))
        if (type(name) is not str or name not in FAMILIES or name in seen
            or not integer(count, 1, 2**53 - 1) or not integer(duration, 0, value["window_ms"])
            or not integer(opened, 0, min(count, 64 - pending))):
            raise ValueError("Invalid database observation")
        seen.add(name)
        pending += opened
        rows.append({"source": name, "observed": count, "longest_ms": duration, "open_at_end": opened})
    return {"schema_version": 1, "kind": "sqlite_write_sample", "coverage": "new_core_engine_connections",
            "window_ms": value["window_ms"], "limited": value["limited"], "families": rows}
