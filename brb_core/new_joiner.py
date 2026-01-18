# brb_core/new_joiner.py

from math import ceil
import pandas as pd
from brb_core.sod_rules import apply_sod_policy


def recommend_access_for_new_joiner(
    df: pd.DataFrame,
    job_code: str,
    supervisor_level6: str | None = None,
    department: str | None = None,
    min_role_support: float = 0.70,
    top_n: int = 15,
    block_high_sod: bool = True,
):
    """
    Rule-based recommendation:
      - filter cohort by job_code + (supervisor OR department)
      - compute role frequency within cohort
      - recommend roles above support threshold
      - apply SoD policy:
          - block HIGH conflicts (remove roles) if block_high_sod=True
          - keep MEDIUM/LOW but flag as warnings

    Returns a DataFrame of recommended roles with coverage stats + reason + SoD info.
    """
    cohort = df[df["job_code"] == job_code].copy()

    if supervisor_level6 is not None:
        cohort = cohort[cohort["supervisor_level6"] == supervisor_level6]
    elif department is not None:
        cohort = cohort[cohort["department"] == department]

    users_in_cohort = cohort["user_id"].nunique()

    if users_in_cohort == 0:
        return pd.DataFrame([{
            "job_code": job_code,
            "supervisor_level6": supervisor_level6,
            "department": department,
            "users_in_cohort": 0,
            "recommended_roles": [],
            "reason": "No users found for this cohort.",
            "sod_conflicts": "[]",
            "sod_removed_roles": "",
            "sod_policy": f"block_high={block_high_sod}",
        }])

    min_count = ceil(min_role_support * users_in_cohort)

    role_counts = (
        cohort.groupby("ar_role_name")["user_id"]
              .nunique()
              .reset_index(name="users_with_role")
              .sort_values("users_with_role", ascending=False)
    )
    role_counts["coverage_pct"] = (role_counts["users_with_role"] / users_in_cohort * 100).round(2)

    # eligible roles above threshold
    eligible = role_counts[role_counts["users_with_role"] >= min_count].head(top_n)

    candidate_roles = eligible["ar_role_name"].tolist()

    # apply SoD policy (block HIGH by default)
    kept_roles, removed_roles, conflicts = apply_sod_policy(candidate_roles, block_high=block_high_sod)

    # output: only roles that survived policy
    out = eligible[eligible["ar_role_name"].isin(kept_roles)].copy()

    out.insert(0, "job_code", job_code)
    out.insert(1, "users_in_cohort", users_in_cohort)
    out.insert(2, "min_role_support", min_role_support)
    out.insert(3, "supervisor_level6", supervisor_level6 if supervisor_level6 is not None else "")
    out.insert(4, "department", department if department is not None else "")

    out["reason"] = out.apply(
        lambda r: f"Role appears in {int(r['users_with_role'])}/{users_in_cohort} users ({r['coverage_pct']}%) in cohort.",
        axis=1
    )

    # same SoD summary on every row (easy to export / audit)
    out["sod_conflicts"] = str(conflicts)
    out["sod_removed_roles"] = ",".join(removed_roles)
    out["sod_policy"] = f"block_high={block_high_sod}"

    return out.reset_index(drop=True)
