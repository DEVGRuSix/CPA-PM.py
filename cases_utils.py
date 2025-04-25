# cases_utils.py
import pandas as pd
from typing import Dict, List, Tuple

def extract_variants(df: pd.DataFrame, case_col: str, act_col: str, time_col: str) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    df_sorted = df.sort_values([case_col, time_col])
    case_groups = df_sorted.groupby(case_col)[act_col].apply(list)
    case_events_map = case_groups.to_dict()
    variants_map: Dict[str, List[str]] = {}
    for case_id, events in case_events_map.items():
        variant_str = ",".join(events)
        variants_map.setdefault(variant_str, []).append(case_id)
    return variants_map, case_events_map

def get_case_event_details(df: pd.DataFrame, case_id: str, case_col: str, time_col: str) -> pd.DataFrame:
    df_case = df[df[case_col] == case_id].copy()
    df_case.sort_values(by=time_col, inplace=True)
    return df_case.reset_index(drop=True)
