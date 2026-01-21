# brb_core/new_joiner.py

from __future__ import annotations

from math import ceil
import pandas as pd

from brb_core.sod_rules import apply_sod_policy, assess_bundle_sod


def _remove_roles_for_high_conflicts(
    roles: list[str],
    high_conflict_pairs: list[tuple[str, str]],
    role_strength: dict[str, int],
) -> tuple[list[str], list[str]]:
    """
    Deterministic removal for HIGH conflicts.
    We remove the *weaker* role in the conflicting pair (lower users_with_role).
    Tie-break: remove the second role in the pair.
    """
    kept = set(roles)
    removed = set()

    for a, b in high_conflict_pairs:
        if a in kept and b in kept:
            sa = role_strength.get(a, 0)
            sb = role_strength.get(b, 0)

            # remove weaker role; if tie, remove b
            drop = a if sa < sb else b if sb < sa else b
            if drop in kept:
                kept.remove(drop)
                removed.add(drop)

    return sorted(kept), sorted(removed)


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
      - filter cohort by job_code + optional supervisor_level6 + optional department
      - compute role frequency within cohort
      - recommend roles above support threshold
      - SoD:
          (1) apply explicit policy rules via apply_sod_policy (uses SOD_RULES)
          (2) assess heuristic SoD risk via assess_bundle_sod (keywords)
          (3) if block_high_sod=True, also remove roles involved in HIGH heuristic conflicts (deterministic)
    """
    # --- cohort filter: always by job_code, then AND supervisor/department if provided ---
    cohort = df[df["job_code"] == job_code].copy()

    if supervisor_level6 is not None and supervisor_level6.strip():
        cohort = cohort[cohort["supervisor_level6"] == supervisor_level6.strip()]

    if department is not None and department.strip():
        cohort = cohort[cohort["department"] == department.strip()]

    users_in_cohort = cohort["user_id"].nunique()

    if users_in_cohort == 0:
        return pd.DataFrame([{
            "job_code": job_code,
            "supervisor_level6": supervisor_level6 or "",
            "department": department or "",
            "users_in_cohort": 0,
            "min_role_support": min_role_support,
            "ar_role_name": "",
            "users_with_role": 0,
            "coverage_pct": 0.0,
            "reason": "No users found for this cohort.",
            "sod_risk": "LOW",
            "sod_conflict_count": 0,
            "sod_conflicts": [],
            "sod_removed_roles": "",
            "sod_policy": f"block_high={block_high_sod} (explicit+heuristic)",
        }]).reset_index(drop=True)

    min_count = ceil(min_role_support * users_in_cohort)

    role_counts = (
        cohort.groupby("ar_role_name")["user_id"]
              .nunique()
              .reset_index(name="users_with_role")
              .sort_values("users_with_role", ascending=False)
    )
    role_counts["coverage_pct"] = (role_counts["users_with_role"] / users_in_cohort * 100).round(2)

    eligible = role_counts[role_counts["users_with_role"] >= min_count].head(top_n).copy()
    candidate_roles = eligible["ar_role_name"].tolist()

    # strength map for deterministic removals
    strength = dict(zip(eligible["ar_role_name"], eligible["users_with_role"]))

    # (1) Explicit SoD enforcement (policy rules)
    kept_roles, removed_rules, rule_conflicts = apply_sod_policy(candidate_roles, block_high=block_high_sod)

    # (2) Heuristic assessment on what remains
    heuristic = assess_bundle_sod(kept_roles)

    # (3) Optional heuristic HIGH enforcement
    removed_heuristic = []
    if block_high_sod and heuristic.get("conflicts"):
        high_pairs = []
        for c in heuristic["conflicts"]:
            if str(c.get("severity", "")).upper() == "HIGH":
                pair = c.get("pair", [])
                if isinstance(pair, list) and len(pair) == 2:
                    high_pairs.append((pair[0], pair[1]))

        if high_pairs:
            kept_roles, removed_heuristic = _remove_roles_for_high_conflicts(
                kept_roles, high_pairs, strength
            )
            # re-assess after removal so reported risk matches final recommendation set
            heuristic = assess_bundle_sod(kept_roles)

    removed_all = sorted(set(removed_rules) | set(removed_heuristic))

    # output only roles that survived enforcement
    out = eligible[eligible["ar_role_name"].isin(kept_roles)].copy()

    out.insert(0, "job_code", job_code)
    out.insert(1, "users_in_cohort", users_in_cohort)
    out.insert(2, "min_role_support", float(min_role_support))
    out.insert(3, "supervisor_level6", supervisor_level6 or "")
    out.insert(4, "department", department or "")

    out["reason"] = out.apply(
        lambda r: f"Role appears in {int(r['users_with_role'])}/{users_in_cohort} users ({r['coverage_pct']}%) in cohort.",
        axis=1
    )

    out["sod_risk"] = heuristic.get("risk", "LOW")
    out["sod_conflict_count"] = len(heuristic.get("conflicts", []))
    out["sod_conflicts"] = [heuristic.get("conflicts", [])] * len(out)  # list per row (JSON safe)
    out["sod_removed_roles"] = ",".join(removed_all)
    out["sod_policy"] = f"block_high={block_high_sod} (explicit+heuristic)"

    return out.reset_index(drop=True)
