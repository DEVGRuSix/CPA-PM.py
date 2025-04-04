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

import pandas as pd
from pm4py.objects.conversion.log import converter as log_converter

def cpa_keep_last(event_log):
    """
    对于每个案例，每种活动保留最后一次出现的事件（按时间排序）
    """
    df = log_converter.apply(event_log, variant=log_converter.Variants.TO_DATA_FRAME)
    if not pd.api.types.is_datetime64_any_dtype(df["time:timestamp"]):
        df["time:timestamp"] = pd.to_datetime(df["time:timestamp"])

    # 排序后保留最后一条
    df_sorted = df.sort_values(by=["case:concept:name", "concept:name", "time:timestamp"], ascending=[True, True, True])
    df_dedup = df_sorted.drop_duplicates(subset=["case:concept:name", "concept:name"], keep="last")

    df_dedup = df_dedup.sort_values(by=["case:concept:name", "time:timestamp"])
    return log_converter.apply(df_dedup, variant=log_converter.Variants.TO_EVENT_LOG)