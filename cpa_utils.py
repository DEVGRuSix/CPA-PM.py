# cpa_utils.py

def keep_first_occurrence_only(event_log):
    """
    对每个 trace，仅保留每个活动的第一次出现
    Args:
        event_log: PM4Py 的 EventLog
    Returns:
        新的 EventLog
    """
    from pm4py.objects.log.obj import EventLog, Trace

    new_log = EventLog()
    for trace in event_log:
        seen = set()
        new_trace = Trace()
        for event in trace:
            act = event.get("concept:name", "undefined")
            if act not in seen:
                new_trace.append(event)
                seen.add(act)
        if new_trace:
            new_log.append(new_trace)
    return new_log
