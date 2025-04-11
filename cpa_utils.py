# cpa_utils.py

import pandas as pd

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


def enrich_with_event_order(df: pd.DataFrame, case_col: str, timestamp_col: str) -> pd.DataFrame:
    """
    对每个 case 内的事件按时间排序后，添加事件序号（event_index）
    """
    df = df.sort_values(by=[case_col, timestamp_col])
    df["event_index"] = df.groupby(case_col).cumcount() + 1
    return df


def enrich_with_duration(df: pd.DataFrame, case_col: str, timestamp_col: str) -> pd.DataFrame:
    """
    添加 duration 字段，表示当前事件与前一事件之间的时间差（单位：秒）
    """
    df = df.sort_values(by=[case_col, timestamp_col])
    df["prev_time"] = df.groupby(case_col)[timestamp_col].shift(1)
    df["duration"] = (df[timestamp_col] - df["prev_time"]).dt.total_seconds()
    df = df.drop(columns=["prev_time"])
    return df


from pm4py.objects.conversion.log import converter as log_converter
import pandas as pd

def merge_duplicate_activities_user_config(df, case_col, activity_col, time_col, target_activity, agg_config):
    """
    将同一 trace 中重复的指定活动进行合并
    agg_config 是一个 dict: {col_name: 'min'|'max'|'avg'|'join'}
    """
    import numpy as np
    from collections import defaultdict

    def aggregate_column(group, method):
        if method == 'min':
            return group.min()
        elif method == 'max':
            return group.max()
        elif method == 'avg':
            return group.mean(numeric_only=True)
        elif method == 'join':
            return '|'.join(group.dropna().astype(str).unique())
        else:
            return group.iloc[0]

    df = df.sort_values([case_col, time_col])
    records = []

    for case_id, group in df.groupby(case_col):
        group = group.copy()
        sub = group[group[activity_col] == target_activity]
        others = group[group[activity_col] != target_activity]

        if len(sub) <= 1:
            records.append(group)
        else:
            row = sub.iloc[0].copy()
            row[time_col] = sub[time_col].min()
            for col, method in agg_config.items():
                if col in sub.columns:
                    row[col] = aggregate_column(sub[col], method)
            records.append(pd.concat([others, pd.DataFrame([row])]))

    result_df = pd.concat(records).sort_values([case_col, time_col])
    return result_df

