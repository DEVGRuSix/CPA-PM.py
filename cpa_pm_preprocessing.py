# cpa_pm_preprocessing.py
import pandas as pd

def remove_events_low_frequency(df, event_col, min_freq):
    """
    删除事件频率低于 min_freq 的行。
    """
    value_counts = df[event_col].value_counts()
    keep_events = value_counts[value_counts >= min_freq].index
    return df[df[event_col].isin(keep_events)].copy()


def delete_traces_with_short_length(df, case_col, min_len):
    """
    删除 trace 长度 < min_len 的行。
    """
    trace_lengths = df[case_col].value_counts()
    keep_cases = trace_lengths[trace_lengths >= min_len].index
    return df[df[case_col].isin(keep_cases)].copy()


def delete_truncated_traces_start(df, case_col, event_col, required_start_event):
    """
    删除未以 required_start_event 开始的 trace。
    """
    first_events = df.sort_values("time:timestamp").groupby(case_col)[event_col].first()
    keep_cases = first_events[first_events == required_start_event].index
    return df[df[case_col].isin(keep_cases)].copy()


def delete_truncated_traces_end(df, case_col, event_col, required_end_event):
    """
    删除未以 required_end_event 结尾的 trace。
    """
    last_events = df.sort_values("time:timestamp").groupby(case_col)[event_col].last()
    keep_cases = last_events[last_events == required_end_event].index
    return df[df[case_col].isin(keep_cases)].copy()


def merge_rows(df, case_col, activity_col, time_col, agg_cols=None, time_strategy='min'):
    """
    合并重复活动行（同 case 同 activity 多行）为一行，按时间排序。
    agg_cols 可指定额外属性字段，如何聚合。
    """
    if agg_cols is None:
        agg_cols = []

    df = df.sort_values([case_col, time_col])
    grouped = df.groupby([case_col, activity_col])

    records = []
    for (case, act), group in grouped:
        row = group.iloc[0].copy()
        row[time_col] = group[time_col].min() if time_strategy == 'min' else group[time_col].max()
        for col in agg_cols:
            row[col] = '|'.join(group[col].dropna().astype(str).unique())
        records.append(row)

    merged_df = pd.DataFrame(records)
    return merged_df.sort_values([case_col, time_col])


def keep_first_occurrence(df, case_col, event_col):
    """
    保留每个 trace 中事件的第一次出现（例如每种活动只保留一次）。
    """
    df = df.sort_values("time:timestamp")
    return df.drop_duplicates(subset=[case_col, event_col], keep="first").copy()


def keep_last_occurrence(df, case_col, event_col):
    """
    保留每个 trace 中事件的最后一次出现。
    """
    df = df.sort_values("time:timestamp")
    return df.drop_duplicates(subset=[case_col, event_col], keep="last").copy()
