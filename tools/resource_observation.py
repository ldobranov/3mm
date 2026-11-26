"""Explain one imported application cgroup sample. No filesystem or systemd access."""
from fractions import Fraction


FIELDS = {"cpu": ("quota_usec", "period_usec"), "memory": ("max_bytes",), "tasks": ("max_tasks",)}
REASONS = {"controller_not_available_on_host", "controller_file_absent", "read_failed", "invalid_value"}


def _number(value, minimum=0):
    if type(value) is not int or not minimum <= value < 2**64:
        raise ValueError("Invalid resource measurement")
    return value


def _cap(resource, raw, *, hierarchy=False):
    if type(raw) is not dict:
        raise ValueError("Missing resource measurement")
    state = raw.get("state")
    allowed = {"os_enforced", "unavailable", "no_visible_cap" if hierarchy else "not_set_here"}
    if type(state) is not str or state not in allowed:
        raise ValueError("Invalid cap state")
    cap = {"state": state}
    if state == "os_enforced":
        cap.update({field: _number(raw.get(field), int(resource == "cpu")) for field in FIELDS[resource]})
    if hierarchy:
        complete = raw.get("complete")
        if type(complete) is not bool or state == "unavailable" and complete or state == "no_visible_cap" and not complete:
            raise ValueError("Invalid hierarchy coverage")
        cap["complete"] = complete
        if state == "os_enforced":
            if raw.get("source") not in ("unit", "parent"):
                raise ValueError("Invalid cap source")
            cap["source"] = raw["source"]
    elif state == "unavailable":
        reason = raw.get("reason")
        if type(reason) is not str or reason not in REASONS:
            raise ValueError("Invalid resource observation reason")
        cap["reason"] = reason
    return cap


def _value(resource, cap):
    return Fraction(*(cap[key] for key in FIELDS[resource]))


def from_service(service, instance):
    """Absent in old evidence is not a zero. Reject mixed units or inconsistent ceilings."""
    observed = ("limits", "hierarchy_limits", "usage")
    if not any(field in service for field in observed):
        return None
    if (service["state"] != "observed" or service.get("unit") != f"3mm-application-extension@{instance}.service"
            or service.get("scope") != "unit_cgroup" or type(service.get("schema_version")) is not int
            or service["schema_version"] != 1):
        raise ValueError("Mixed service observations")
    result = {}
    for group, hierarchy in (("limits", False), ("hierarchy_limits", True)):
        if group not in service:
            continue
        if type(service[group]) is not dict:
            raise ValueError("Invalid resource collection")
        result[group] = {r: _cap(r, service[group].get(r), hierarchy=hierarchy) for r in FIELDS}
    if "usage" in service:
        raw = service["usage"]
        if type(raw) is not dict or not {"memory_bytes", "tasks"} <= raw.keys():
            raise ValueError("Invalid usage observation")
        result["usage"] = {k: None if raw[k] is None else _number(raw[k]) for k in ("memory_bytes", "tasks")}
    if "limits" in result and "hierarchy_limits" in result:
        for r, ceiling in result["hierarchy_limits"].items():
            local = result["limits"][r]
            if ceiling.get("source") == "unit" and (local["state"] != "os_enforced" or _value(r, local) != _value(r, ceiling)):
                raise ValueError("Unmatched unit ceiling")
            if local["state"] == "os_enforced" and (ceiling["state"] != "os_enforced"
                    or ceiling["source"] == "parent" and _value(r, ceiling) >= _value(r, local)):
                raise ValueError("Inconsistent hierarchy ceiling")
            if local["state"] == "unavailable" and ceiling["complete"]:
                raise ValueError("Unverified unit ceiling")
    return result


def lines(sample):
    def cap_text(resource, cap):
        if cap is None:
            return "not captured"
        if cap["state"] != "os_enforced":
            return {"not_set_here": "not set on this service", "no_visible_cap": "no cap found in the visible groups",
                    "unavailable": ("controller unavailable on host" if cap.get("reason") == "controller_not_available_on_host"
                                    else "unavailable")}[cap["state"]]
        if resource == "cpu":
            return f"{_value(resource, cap)} CPU of bandwidth ({cap['quota_usec']}/{cap['period_usec']} us quota/period)"
        return str(cap[FIELDS[resource][0]]) + (" bytes" if resource == "memory" else " tasks")

    yield "Saved service limits (not current load or guaranteed capacity):"
    for resource, title in (("cpu", "CPU"), ("memory", "RAM"), ("tasks", "Tasks")):
        local = sample.get("limits", {}).get(resource)
        ceiling = sample.get("hierarchy_limits", {}).get(resource)
        detail = cap_text(resource, ceiling)
        if ceiling and ceiling.get("source") == "parent":
            detail += " (shared parent)"
        if ceiling and not ceiling["complete"]:
            detail += " (hierarchy incomplete)"
        yield f"{title}: service {cap_text(resource, local)}; visible ceiling {detail}."
    if "usage" in sample:
        usage = sample["usage"]
        ram = "unavailable" if usage["memory_bytes"] is None else f"{usage['memory_bytes']} bytes"
        tasks = "unavailable" if usage["tasks"] is None else str(usage["tasks"])
        yield f"Usage at capture: RAM {ram}; tasks (including threads) {tasks}."
