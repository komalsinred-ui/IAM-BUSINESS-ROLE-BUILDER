from itertools import combinations
from math import ceil
import pandas as pd


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


def _support_of_itemset_in_df(df: pd.DataFrame, itemset: tuple) -> tuple[int, int, float]:
    """
    Returns (users_covered, users_in_scope, support)
    support = users_covered / users_in_scope
    """
    user_roles = build_user_role_map(df)
    n_users = len(user_roles)
    if n_users == 0:
        return 0, 0, 0.0

    covered = 0
    itemset_set = set(itemset)
    for roles in user_roles.values():
        if itemset_set.issubset(roles):
            covered += 1

    return covered, n_users, covered / n_users


def _choose_tag(coverages: dict, min_itemset_support: float) -> tuple[str, str]:
    """
    coverages dict:
      {"global": 0.52, "job": 0.71, "dept": 0.69, "supervisor": 0.74}
    Choose the strongest basis that passes threshold, with a priority order.
    """
    # Priority reflects business semantics
    priority = [
        ("global", "Birthright Role"),
        ("job", "Job-Based Role"),
        ("dept", "Department Role"),
        ("supervisor", "Team/Supervisor Role"),
    ]

    # Pick highest support among those passing threshold, tie-break with priority
    candidates = [(basis, label, coverages.get(basis, 0.0)) for basis, label in priority]
    passing = [c for c in candidates if c[2] >= min_itemset_support]

    if not passing:
        # No tag qualifies; return the best-effort tag to explain why it was suggested only in subgroup
        best = max(candidates, key=lambda x: x[2])
        return "Weak/Local Pattern", f"Best basis={best[0]} support={best[2]:.2%} < threshold={min_itemset_support:.2%}"

    best = max(passing, key=lambda x: (x[2], -[p[0] for p in priority].index(x[0])))
    return best[1], f"basis={best[0]} support={best[2]:.2%}"


def suggest_itemsets(
    df: pd.DataFrame,
    group_cols=("supervisor_level6", "job_code", "department"),
    min_role_support=0.60,
    min_itemset_support=0.70,
    max_k=3,
    min_group_size=10,
):
    suggestions = []

    # Precompute scopes for tagging
    # Global scope: entire df
    global_df = df

    for group_key, gdf in df.groupby(list(group_cols)):
        user_roles = build_user_role_map(gdf)
        n_users = len(user_roles)

        if n_users < min_group_size:
            continue

        min_role_count = ceil(min_role_support * n_users)
        min_itemset_count = ceil(min_itemset_support * n_users)

        # singles
        role_counts = _count_singles(user_roles)
        frequent_roles = sorted([r for r, c in role_counts.items() if c >= min_role_count])

        if len(frequent_roles) < 2:
            continue

        # unpack group_key
        key_map = dict(zip(group_cols, group_key if isinstance(group_key, tuple) else (group_key,)))
        sup = key_map.get("supervisor_level6")
        job = key_map.get("job_code")
        dept = key_map.get("department")

        # build alternate scopes
        supervisor_df = df[df["supervisor_level6"] == sup]
        job_df = df[df["job_code"] == job]
        dept_df = df[df["department"] == dept]

        for k in range(2, max_k + 1):
            if len(frequent_roles) < k:
                break

            itemset_counts = _count_itemsets_k(user_roles, frequent_roles, k)

            for itemset, c in itemset_counts.items():
                if c < min_itemset_count:
                    continue

                # compute supports in multiple bases
                _, _, sup_local = _support_of_itemset_in_df(gdf, itemset)
                _, _, sup_job = _support_of_itemset_in_df(job_df, itemset)
                _, _, sup_dept = _support_of_itemset_in_df(dept_df, itemset)
                _, _, sup_global = _support_of_itemset_in_df(global_df, itemset)

                coverages = {
                    "supervisor": sup_local,
                    "job": sup_job,
                    "dept": sup_dept,
                    "global": sup_global,
                }

                tag, tag_reason = _choose_tag(coverages, min_itemset_support)

                suggestions.append({
                    **key_map,
                    "bundle_roles": list(itemset),
                    "bundle_size": k,
                    "users_in_group": n_users,
                    "users_covered": c,
                    "coverage_pct": round(sup_local * 100, 2),
                    "suggestion_tag": tag,
                    "tag_reason": tag_reason,
                    "coverage_by_basis": {k: round(v * 100, 2) for k, v in coverages.items()},
                    "reason": f"Itemset appears in {c}/{n_users} users ({sup_local:.2%}) in this group."
                })

    return pd.DataFrame(suggestions)
