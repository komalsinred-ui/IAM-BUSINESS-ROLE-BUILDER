import pandas as pd


def role_usage_metrics(df: pd.DataFrame, group_cols=("department",)):
    users_per_group = df.groupby(list(group_cols))["user_id"].nunique().reset_index(name="users_in_group")

    role_users = (
        df.groupby(list(group_cols) + ["ar_role_name"])["user_id"]
          .nunique()
          .reset_index(name="users_with_role")
    )

    out = role_users.merge(users_per_group, on=list(group_cols), how="left")
    out["role_coverage_pct"] = (out["users_with_role"] / out["users_in_group"] * 100).round(2)

    return out.sort_values(list(group_cols) + ["role_coverage_pct"], ascending=[True] * len(group_cols) + [False])


def user_access_summary(df: pd.DataFrame):
    role_counts = df.groupby("user_id")["ar_role_name"].nunique().reset_index(name="role_count")

    meta = (
        df.groupby("user_id")
          .agg(
              department=("department", "first"),
              job_code=("job_code", "first"),
              supervisor_level6=("supervisor_level6", "first"),
              assignment_types=("assignment_type", lambda x: ",".join(sorted(set(map(str, x)))))
          )
          .reset_index()
    )

    return meta.merge(role_counts, on="user_id", how="left").sort_values("role_count", ascending=False)


def role_overlap_jaccard(df: pd.DataFrame, min_common_users=3, top_n=50):
    role_to_users = {}
    for role, g in df.groupby("ar_role_name"):
        role_to_users[role] = set(g["user_id"].unique())

    roles = sorted(role_to_users.keys())
    results = []

    for i in range(len(roles)):
        a = roles[i]
        Ua = role_to_users[a]
        for j in range(i + 1, len(roles)):
            b = roles[j]
            Ub = role_to_users[b]

            inter = len(Ua & Ub)
            if inter < min_common_users:
                continue

            union = len(Ua | Ub)
            jac = inter / union if union else 0.0

            results.append({
                "role_a": a,
                "role_b": b,
                "common_users": inter,
                "union_users": union,
                "jaccard": round(jac, 4)
            })

    out = pd.DataFrame(results)
    if out.empty:
        return out

    return out.sort_values(["jaccard", "common_users"], ascending=False).head(top_n)
