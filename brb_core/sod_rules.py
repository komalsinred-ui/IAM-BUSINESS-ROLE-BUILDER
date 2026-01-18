# brb_core/sod_rules.py

"""
Severity-based SoD rules + simple enforcement policy.

- SOD_RULES: list of conflict rules, each has:
    a: role name
    b: role name
    severity: LOW | MEDIUM | HIGH
    reason: short explanation
- apply_sod_policy:
    - blocks HIGH by default (removes 'b' role in each HIGH conflict)
    - MEDIUM/LOW are warnings (kept) but returned in conflicts list
"""

SOD_RULES = [
    # 🔻 Replace these examples with your real SoD rules later
    # {"a": "AR_FIN_1", "b": "AR_FIN_2", "severity": "HIGH", "reason": "Maker-checker violation"},
    # {"a": "AR_OPS_3", "b": "AR_OPS_4", "severity": "MEDIUM", "reason": "Privileged + monitoring overlap"},
]

SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


def detect_sod_conflicts(candidate_roles):
    """
    candidate_roles: iterable[str]
    Returns list of conflicts found:
      {a, b, severity, reason}
    """
    roles = set(candidate_roles)
    conflicts = []

    for rule in SOD_RULES:
        a, b = rule["a"], rule["b"]
        if a in roles and b in roles:
            conflicts.append({
                "a": a,
                "b": b,
                "severity": str(rule.get("severity", "MEDIUM")).upper(),
                "reason": str(rule.get("reason", "")),
            })

    # Sort conflicts for stable output: HIGH first, then MEDIUM, then LOW
    conflicts.sort(key=lambda c: SEVERITY_RANK.get(c["severity"], 2), reverse=True)
    return conflicts


def apply_sod_policy(candidate_roles, block_high=True):
    """
    Policy:
      - If block_high=True: remove one role for HIGH conflicts (naively removes 'b')
      - MEDIUM/LOW are warnings only (not removed)

    Returns:
      kept_roles: sorted list[str]
      removed_roles: sorted list[str]
      conflicts: list[dict]
    """
    roles = set(candidate_roles)
    conflicts = detect_sod_conflicts(roles)

    removed = set()
    if block_high:
        for c in conflicts:
            if c["severity"] == "HIGH":
                # naive removal: remove the 'b' role
                if c["b"] in roles:
                    roles.remove(c["b"])
                    removed.add(c["b"])

    return sorted(roles), sorted(removed), conflicts
