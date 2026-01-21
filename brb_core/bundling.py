# brb_core/bundling.py
from itertools import combinations
from math import ceil
import pandas as pd

from brb_core.sod_rules import assess_bundle_sod


def confidence_tier(coverage_pct: float) -> str:
    if coverage_pct >= 80.0:
        return "STRONG"
    if coverage_pct >= 60.0:
        return "MEDIUM"
    return "WEAK"


def build_user_role_map(gdf: pd.DataFrame) -> dict:
    user_roles = {}
    for user, role in zip(gdf["user_id"], gdf["ar_role_name"]):
        user_roles.setdefault(user, set()).add(role)
    return user_roles


def _count_singles(user_roles: dict) -> dict:
    counts = {}
    for roles in user_roles.values():
        for r in roles:
            counts[r] = counts.get(r, 0) + 1
    return counts


def _count_itemsets_k(user_roles: dict, frequent_items: list, k: int) -> dict:
    candidates = list(combinations(sorted(frequent_items), k))
    counts = {cand: 0 for cand in candidates}

    for roles in user_roles.values():
        rset = set(roles)
        for cand in candidates:
            if set(cand).issubset(rset):
                counts[cand] += 1

    return counts


def suggest_itemsets(
    df: pd.DataFrame,
    group_cols=("supervisor_level6", "job_code", "department"),
    min_role_support=0.60,
    min_itemset_support=0.70,
    max_k=3,
    min_group_size=10,
) -> pd.DataFrame:
    """
    Suggest bundle candidates (pairs, triples...) by support within each group.

    - role_support(r)    = users_with_role / users_in_group
    - itemset_support(S) = users_with_all_roles_in_S / users_in_group

    Key behavior:
    - Dynamic itemset support for small cohorts:
        n_users <= 12  -> effective <= 0.60
        n_users <= 25  -> effective <= 0.65
        else           -> requested min_itemset_support
    - Always returns a DataFrame with a stable schema (even when empty)
    """

    expected_cols = list(group_cols) + [
        "bundle_roles",
        "bundle_size",
        "users_in_group",
        "users_covered",
        "coverage_pct",
        "confidence_tier",
        "requested_min_itemset_support",
        "effective_itemset_support",
        "min_itemset_count",
        "explain",
        "sod_risk",
        "sod_conflict_count",
        "sod_conflicts",
    ]

    suggestions = []

    # Defensive: if df is empty or missing required columns, return empty stable DF
    if df is None or df.empty:
        return pd.DataFrame(columns=expected_cols)

    required_cols = {"user_id", "ar_role_name", *group_cols}
    missing = required_cols - set(df.columns)
    if missing:
        # Return stable DF; upstream can diagnose missing columns without crashing
        return pd.DataFrame(columns=expected_cols)

    for group_key, gdf in df.groupby(list(group_cols), dropna=False):
        user_roles = build_user_role_map(gdf)
        n_users = len(user_roles)

        if n_users < min_group_size:
            continue

        # ---- Dynamic itemset support adjustment for small cohorts ----
        effective_itemset_support = float(min_itemset_support)
        if n_users <= 12:
            effective_itemset_support = min(effective_itemset_support, 0.60)
        elif n_users <= 25:
            effective_itemset_support = min(effective_itemset_support, 0.65)

        min_role_count = ceil(float(min_role_support) * n_users)
        min_itemset_count = ceil(float(effective_itemset_support) * n_users)

        # 1) Frequent singles
        role_counts = _count_singles(user_roles)
        frequent_roles = sorted([r for r, c in role_counts.items() if c >= min_role_count])
        if len(frequent_roles) < 2:
            continue

        # Unpack group key
        key_map = dict(zip(group_cols, group_key if isinstance(group_key, tuple) else (group_key,)))

        # 2) Count k-itemsets
        for k in range(2, int(max_k) + 1):
            if len(frequent_roles) < k:
                break

            itemset_counts = _count_itemsets_k(user_roles, frequent_roles, k)

            for itemset, covered in itemset_counts.items():
                if covered < min_itemset_count:
                    continue

                support = covered / n_users
                coverage_pct = round(support * 100, 2)
                tier = confidence_tier(coverage_pct)

                # SoD assessment (rule-based right now)
                sod = assess_bundle_sod(itemset)
                sod_risk = sod.get("risk", "NONE")
                sod_conflicts = sod.get("conflicts", []) or []
                sod_conflict_count = len(sod_conflicts)

                explain = (
                    f"Covered {covered}/{n_users} = {support:.2%}. "
                    f"Requested min_itemset_support={float(min_itemset_support):.2f}. "
                    f"Effective min_itemset_support={float(effective_itemset_support):.2f} "
                    f"(min_count={min_itemset_count}). "
                    f"SoD={sod_risk} ({sod_conflict_count} conflicts)."
                )

                suggestions.append({
                    **key_map,
                    "bundle_roles": list(itemset),
                    "bundle_size": int(k),
                    "users_in_group": int(n_users),
                    "users_covered": int(covered),
                    "coverage_pct": float(coverage_pct),
                    "confidence_tier": tier,
                    "requested_min_itemset_support": float(min_itemset_support),
                    "effective_itemset_support": float(effective_itemset_support),
                    "min_itemset_count": int(min_itemset_count),
                    "explain": explain,
                    "sod_risk": sod_risk,
                    "sod_conflict_count": int(sod_conflict_count),
                    "sod_conflicts": sod_conflicts,
                })

    out = pd.DataFrame(suggestions)

    # ✅ Always return stable schema (prevents KeyError downstream)
    if out.empty:
        return pd.DataFrame(columns=expected_cols)

    # Sorting
    tier_rank = {"STRONG": 0, "MEDIUM": 1, "WEAK": 2}
    sod_rank = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}

    out["tier_rank"] = out["confidence_tier"].map(tier_rank).fillna(9).astype(int)
    out["sod_rank"] = out["sod_risk"].map(sod_rank).fillna(9).astype(int)

    # Sort: strongest confidence first, then lower SoD risk first, then highest coverage, then larger bundles
    out = out.sort_values(
        by=["tier_rank", "sod_rank", "coverage_pct", "bundle_size"],
        ascending=[True, True, False, False],
    ).drop(columns=["tier_rank", "sod_rank"])

    # Ensure column order is consistent (optional but nice)
    out = out.reindex(columns=expected_cols)

    return out
