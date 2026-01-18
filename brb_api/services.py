#loads data + calls Phase 1 functions

import pandas as pd
from brb_core.bundling import suggest_itemsets
from brb_core.metrics import role_usage_metrics, user_access_summary, role_overlap_jaccard
from brb_core.new_joiner import recommend_access_for_new_joiner
from itertools import combinations
from collections import Counter
from math import ceil

DATA_PATH = "data/synthetic_iam_extract.csv"

def load_data() -> pd.DataFrame:
    return pd.read_csv(DATA_PATH)

def filter_df(df: pd.DataFrame, supervisor_level6=None, department=None, job_code=None, assignment_type=None):
    out = df.copy()
    if supervisor_level6:
        out = out[out["supervisor_level6"] == supervisor_level6]
    if department:
        out = out[out["department"] == department]
    if job_code:
        out = out[out["job_code"] == job_code]
    if assignment_type:
        out = out[out["assignment_type"] == assignment_type]
    return out

def query_bundles(df: pd.DataFrame, req):
    # Use stable grouping for now (Phase 1 proven)
    bundles = suggest_itemsets(
        df,
        group_cols=("supervisor_level6", "job_code"),
        min_role_support=req.min_role_support,
        min_itemset_support=req.min_itemset_support,
        max_k=req.max_k,
        min_group_size=req.min_group_size
    )
    # filter output rows if user asked for specific filters
    if req.supervisor_level6:
        bundles = bundles[bundles["supervisor_level6"] == req.supervisor_level6]
    if req.job_code:
        bundles = bundles[bundles["job_code"] == req.job_code]
    if req.assignment_type and "assignment_type" in bundles.columns:
        bundles = bundles[bundles["assignment_type"] == req.assignment_type]
    return bundles

def get_role_metrics(df: pd.DataFrame, req):
    f = filter_df(df, req.supervisor_level6, req.department, req.job_code, req.assignment_type)
    return role_usage_metrics(f, group_cols=("department",))

def get_user_summary(df: pd.DataFrame, req):
    f = filter_df(df, req.supervisor_level6, req.department, req.job_code, req.assignment_type)
    return user_access_summary(f)

def get_overlap(df: pd.DataFrame, min_common_users=5, top_n=50):
    return role_overlap_jaccard(df, min_common_users=min_common_users, top_n=top_n)

def new_joiner(df: pd.DataFrame, req):
    return recommend_access_for_new_joiner(
        df,
        job_code=req.job_code,
        supervisor_level6=req.supervisor_level6,
        department=req.department,
        min_role_support=req.min_role_support,
        top_n=req.top_n,
        block_high_sod=req.block_high_sod
    )

def diagnose_bundles(df: pd.DataFrame, req):
    """
    Explain why bundles are empty / sparse.

    Returns:
      - groups_checked
      - groups_below_min_size
      - top_single_roles (support)
      - top_pairs / top_triples (support)
      - best_observed_support vs thresholds
      - blocking_reason (human-readable)
    """
    f = filter_df(df, req.supervisor_level6, req.department, req.job_code, req.assignment_type if hasattr(req, "assignment_type") else None)

    # We'll diagnose on the same grouping strategy used in query_bundles
    group_cols = ["supervisor_level6", "job_code"]
    if req.department:
        # optional: if department is specified, add it to grouping for tighter diagnostics
        group_cols = ["supervisor_level6", "job_code", "department"]

    groups_checked = 0
    groups_below = 0

    best_pair_support = 0.0
    best_triple_support = 0.0
    best_pair = None
    best_triple = None

    single_counter = Counter()
    user_count_total = 0

    # helper: user -> set(roles) for a group
    def user_role_map(gdf):
        m = {}
        for u, r in zip(gdf["user_id"], gdf["ar_role_name"]):
            m.setdefault(u, set()).add(r)
        return m

    for _, gdf in f.groupby(group_cols):
        groups_checked += 1
        uroles = user_role_map(gdf)
        n_users = len(uroles)

        if n_users < req.min_group_size:
            groups_below += 1
            continue

        user_count_total += n_users

        # single counts in this group
        role_counts = Counter()
        for rs in uroles.values():
            role_counts.update(rs)

        # accumulate for global/top singles view
        single_counter.update(role_counts)

        min_role_count = ceil(req.min_role_support * n_users)
        frequent_roles = [r for r, c in role_counts.items() if c >= min_role_count]

        if len(frequent_roles) < 2:
            continue

        # evaluate top pairs (support)
        # only check candidates made from frequent roles (pruning)
        for a, b in combinations(sorted(frequent_roles), 2):
            covered = sum(1 for rs in uroles.values() if a in rs and b in rs)
            sup = covered / n_users
            if sup > best_pair_support:
                best_pair_support = sup
                best_pair = (a, b, covered, n_users)

        # evaluate top triples if asked
        if req.max_k >= 3 and len(frequent_roles) >= 3:
            for a, b, c in combinations(sorted(frequent_roles), 3):
                covered = sum(1 for rs in uroles.values() if a in rs and b in rs and c in rs)
                sup = covered / n_users
                if sup > best_triple_support:
                    best_triple_support = sup
                    best_triple = (a, b, c, covered, n_users)

    # Build readable top singles by approximate support
    # We compute support as (users_with_role / users_in_group) approx; since we aggregated counts across groups,
    # we normalize by the total users counted in eligible groups as a rough diagnostic.
    top_singles = []
    if user_count_total > 0:
        for role, c in single_counter.most_common(req.top_n):
            top_singles.append({
                "role": role,
                "approx_support_pct": round((c / user_count_total) * 100, 2),
                "count": c
            })

    # Determine blocking reason
    reasons = []
    if groups_checked == 0:
        reasons.append("No groups found after filtering.")
    else:
        if groups_below == groups_checked:
            reasons.append(f"All groups below min_group_size={req.min_group_size}.")
        if best_pair_support < req.min_itemset_support:
            reasons.append(
                f"min_itemset_support too high: best_pair_support={best_pair_support:.2%} < {req.min_itemset_support:.2%}"
            )
        if req.max_k >= 3 and best_triple_support < req.min_itemset_support:
            reasons.append(
                f"best_triple_support={best_triple_support:.2%} < {req.min_itemset_support:.2%}"
            )
        if not reasons:
            reasons.append("Thresholds allow bundles; if count is still low, data may be sparse for selected filters.")

    out = {
        "groups_checked": groups_checked,
        "groups_below_min_size": groups_below,
        "min_group_size": req.min_group_size,
        "min_role_support": req.min_role_support,
        "min_itemset_support": req.min_itemset_support,
        "top_single_roles": top_singles,
        "best_pair": None,
        "best_pair_support_pct": round(best_pair_support * 100, 2),
        "best_triple": None,
        "best_triple_support_pct": round(best_triple_support * 100, 2),
        "blocking_reason": " | ".join(reasons),
    }

    if best_pair:
        a, b, covered, n_users = best_pair
        out["best_pair"] = {"roles": [a, b], "covered": covered, "users_in_group": n_users}

    if best_triple:
        a, b, c, covered, n_users = best_triple
        out["best_triple"] = {"roles": [a, b, c], "covered": covered, "users_in_group": n_users}

    return out

