# cpa_utils.py

import pandas as pd

def filter_events_by_global_frequency(df, event_col="concept:name", min_freq=1):
    """
    删除出现频率小于 min_freq 的事件行（保留 trace 结构）。
    """
    value_counts = df[event_col].value_counts()
    keep_events = value_counts[value_counts >= min_freq].index
    return df[df[event_col].isin(keep_events)].copy()

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

def merge_activities_in_dataframe(df, activities, new_name):
    """
    将多个活动合并为一个（保留首次时间）
    """
    df = df.copy()
    df["is_target"] = df["concept:name"].isin(activities)

    merged_rows = []
    for case_id, group in df[df["is_target"]].groupby("case:concept:name"):
        row = group.iloc[0].copy()
        row["concept:name"] = new_name
        row["time:timestamp"] = group["time:timestamp"].min()
        merged_rows.append(row)

    df = df[~df["is_target"]]
    df = pd.concat([df, pd.DataFrame(merged_rows)], ignore_index=True)
    df = df.drop(columns=["is_target"])
    df = df.sort_values(by=["case:concept:name", "time:timestamp"])
    return df



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

from pm4py.objects.conversion.log import converter as log_converter
import pandas as pd

def filter_traces_by_start_event(event_log, required_start_event):
    '''
    保留以 required_start_event 开头的 trace
    '''
    filtered_log = []
    for trace in event_log:
        if len(trace) > 0 and trace[0].get("concept:name") == required_start_event:
            filtered_log.append(trace)
    return filtered_log

def filter_traces_by_end_event(event_log, required_end_event):
    '''
    保留以 required_end_event 结尾的 trace
    '''
    filtered_log = []
    for trace in event_log:
        if len(trace) > 0 and trace[-1].get("concept:name") == required_end_event:
            filtered_log.append(trace)
    return filtered_log

def apply_merge_operations(event_log, ops_list):
    df = log_converter.apply(event_log, variant=log_converter.Variants.TO_DATA_FRAME)

    for op in ops_list:
        acts = op["activities"]
        new_name = op["new_name"]
        strategy = op["strategy"]
        fields = op["fields"]

        df = df[df["concept:name"].notna()]
        df["is_merge_target"] = df["concept:name"].isin(acts)

        grouped = df[df["is_merge_target"]].groupby("case:concept:name")

        merged_rows = []
        for case, group in grouped:
            row = group.iloc[0].copy()
            if strategy == "first":
                row["time:timestamp"] = group["time:timestamp"].min()
            elif strategy == "last":
                row["time:timestamp"] = group["time:timestamp"].max()
            else:
                row["time:timestamp"] = group["time:timestamp"].min()

            row["concept:name"] = new_name
            for field in fields:
                vals = group[field].dropna().astype(str).unique()
                row[field] = "|".join(vals)
            merged_rows.append(row)

        df = df[~df["is_merge_target"]]
        df = pd.concat([df] + merged_rows, ignore_index=True)
        df = df.drop(columns=["is_merge_target"])
        df = df.sort_values(by=["case:concept:name", "time:timestamp"])

    return log_converter.apply(df, variant=log_converter.Variants.TO_EVENT_LOG)


def apply_activity_merge_rules(event_log, rule_list):
    """
    根据多个 merge 规则合并事件
    """
    df = log_converter.apply(event_log, variant=log_converter.Variants.TO_DATA_FRAME)
    df["lifecycle:transition"] = "complete"
    if not pd.api.types.is_datetime64_any_dtype(df["time:timestamp"]):
        df["time:timestamp"] = pd.to_datetime(df["time:timestamp"])

    all_new_rows = []
    for case, group in df.groupby("case:concept:name"):
        new_rows = []
        skip_idx = set()
        for rule in rule_list:
            src_acts = rule["source_activities"]
            target = rule["target_activity"]
            strategy = rule["strategy"]
            agg_cols = rule.get("agg_columns", [])

            mask = group["concept:name"].isin(src_acts)
            group_sub = group[mask]
            if not group_sub.empty:
                row = group_sub.iloc[0].copy()
                row["concept:name"] = target
                if strategy == "first":
                    row["time:timestamp"] = group_sub["time:timestamp"].min()
                elif strategy == "last":
                    row["time:timestamp"] = group_sub["time:timestamp"].max()
                elif strategy == "average":
                    row["time:timestamp"] = group_sub["time:timestamp"].mean()

                for col in agg_cols:
                    row[col] = "|".join(group_sub[col].dropna().astype(str).unique())
                new_rows.append(row)
                skip_idx.update(group_sub.index.tolist())

        group_remain = group.drop(index=skip_idx)
        all_new_rows.extend(group_remain.to_dict("records") + [r.to_dict() for r in new_rows])

    new_df = pd.DataFrame(all_new_rows)
    new_df = new_df.sort_values(by=["case:concept:name", "time:timestamp"])
    new_df["lifecycle:transition"] = "complete"
    return log_converter.apply(new_df, variant=log_converter.Variants.TO_EVENT_LOG)

def merge_activities_in_event_log(event_log, activities_to_merge, new_activity="merged", keep="first"):
    """
    将多个活动合并为新活动名，保留其 first 或 last 出现时间。

    Args:
        event_log: PM4Py EventLog
        activities_to_merge: 要合并的活动名列表
        new_activity: 合并后的新活动名
        keep: 保留 'first' 或 'last' 时间

    Returns:
        新 EventLog
    """
    df = log_converter.apply(event_log, variant=log_converter.Variants.TO_DATA_FRAME)
    if not pd.api.types.is_datetime64_any_dtype(df["time:timestamp"]):
        df["time:timestamp"] = pd.to_datetime(df["time:timestamp"])

    df = df.sort_values(by=["case:concept:name", "time:timestamp"])

    grouped = df[df["concept:name"].isin(activities_to_merge)].groupby("case:concept:name")
    replace_df = []

    for case, group in grouped:
        if keep == "first":
            row = group.iloc[0].copy()
        else:
            row = group.iloc[-1].copy()
        row["concept:name"] = new_activity
        replace_df.append(row)

    df = df[~df["concept:name"].isin(activities_to_merge)]
    df = pd.concat([df, pd.DataFrame(replace_df)], ignore_index=True)
    df = df.sort_values(by=["case:concept:name", "time:timestamp"])

    return log_converter.apply(df, variant=log_converter.Variants.TO_EVENT_LOG)

def aggregate_activity_occurrences(df, target_activity, keep="first", timestamp_col="time:timestamp", agg_fields=None, new_col=None):

    """
    对每个 trace 内，聚合某个重复出现的活动，仅保留一次（保留首次或最后），并对其他字段聚合。

    Parameters:
        df: pd.DataFrame
        target_activity: 需要聚合的活动名称
        keep: "first" 或 "last"
        timestamp_col: 时间字段名
        agg_fields: 需要聚合的字段名列表（如 ["org:resource"]）

    Returns:
        df: 处理后的 DataFrame
    """
    import numpy as np

    df = df.copy()
    df[timestamp_col] = pd.to_datetime(df[timestamp_col])
    df = df.sort_values(by=["case:concept:name", timestamp_col])

    result = []

    for case_id, group in df.groupby("case:concept:name"):
        group = group.copy()
        to_agg = group[group["concept:name"] == target_activity]
        others = group[group["concept:name"] != target_activity]

        if to_agg.empty:
            result.append(group)
            continue

        if keep == "first":
            row = to_agg.iloc[0].copy()
        else:
            row = to_agg.iloc[-1].copy()

        if agg_fields:
            for field in agg_fields:
                values = to_agg[field].dropna().astype(str).unique()
                joined = "|".join(values)
                if new_col:
                    row[new_col] = joined  # ✅ 聚合写入新列
                else:
                    row[field] = joined  # ✅ 覆盖原列

        merged = pd.concat([others, pd.DataFrame([row])], ignore_index=True)
        merged = merged.sort_values(by=timestamp_col)
        result.append(merged)

    new_df = pd.concat(result, ignore_index=True)
    return new_df

def filter_incomplete_traces(df, start_event=None, end_event=None, mode="不同时满足起止"):
    df = df.sort_values("time:timestamp")
    keep_cases = set(df['case:concept:name'].unique())

    if "起始" in mode or "起止" in mode:
        first_events = df.groupby("case:concept:name")["concept:name"].first()
        keep_start = set(first_events[first_events == start_event].index)
        if "起止" in mode:
            keep_cases &= keep_start
        else:
            keep_cases = keep_start

    if "结束" in mode or "起止" in mode:
        last_events = df.groupby("case:concept:name")["concept:name"].last()
        keep_end = set(last_events[last_events == end_event].index)
        if "起止" in mode:
            keep_cases &= keep_end
        else:
            keep_cases = keep_end

    return df[df["case:concept:name"].isin(keep_cases)].copy()

def remove_consecutive_self_loops(df, case_col="case:concept:name", act_col="concept:name", time_col="time:timestamp", keep="first"):
    """
    移除每条 trace 中相邻重复的活动，仅保留首次或最后一次出现。
    非相邻的相同活动不受影响。
    """
    import pandas as pd
    result = []
    df = df.sort_values(by=[case_col, time_col]).copy()

    for case_id, group in df.groupby(case_col):
        group = group.copy()
        keep_rows = []

        acts = group[act_col].tolist()
        indices = group.index.tolist()

        i = 0
        while i < len(acts):
            j = i
            while j + 1 < len(acts) and acts[j + 1] == acts[i]:
                j += 1
            if keep == "first":
                keep_rows.append(indices[i])
            elif keep == "last":
                keep_rows.append(indices[j])
            i = j + 1

        result.append(group.loc[keep_rows])

    final_df = pd.concat(result).sort_values(by=[case_col, time_col])
    return final_df

def filter_traces_containing_start_end(df, start_event=None, end_event=None):
    """
    保留包含起始事件和结束事件，且顺序正确的 trace。
    - 若只填 start_event，则保留包含该事件的流程
    - 若只填 end_event，则保留包含该事件的流程
    - 若两者都填，start 必须在 end 之前
    """
    df = df.sort_values(["case:concept:name", "time:timestamp"])
    keep_cases = []

    for case_id, group in df.groupby("case:concept:name"):
        events = group["concept:name"].tolist()
        if start_event and end_event:
            if start_event in events and end_event in events:
                if events.index(start_event) < events.index(end_event):
                    keep_cases.append(case_id)
        elif start_event:
            if start_event in events:
                keep_cases.append(case_id)
        elif end_event:
            if end_event in events:
                keep_cases.append(case_id)

    return df[df["case:concept:name"].isin(keep_cases)].copy()
