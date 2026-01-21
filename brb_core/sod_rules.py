# brb_core/sod_rules.py

"""
Severity-based SoD rules + simple enforcement policy.

What this file supports:
- detect_sod_conflicts(candidate_roles): rule-based conflicts from SOD_RULES
- apply_sod_policy(candidate_roles, block_high=True): remove roles for HIGH conflicts (naive)
- assess_bundle_sod(bundle_roles): returns risk + conflicts (rule-based + heuristic)

NOTE:
- assess_bundle_sod() is a heuristic layer (good for triage), not a replacement for official SoD policy tooling.
"""

from __future__ import annotations

from typing import Dict, List, Iterable, Tuple

SOD_RULES = [
    # Add real org rules here later, examples:
    # {"a": "AR_FIN_PAYMENTS_INIT", "b": "AR_FIN_PAYMENTS_APPROVE", "severity": "HIGH", "reason": "Maker-checker violation"},
    # {"a": "AR_PRIV_DB_ADMIN", "b": "AR_PRIV_AUDIT_VIEW", "severity": "MEDIUM", "reason": "Privileged + monitoring overlap"},
]

SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}

# Heuristic keyword buckets (customize over time)
HIGH_RISK_KEYWORDS = {
    "admin", "root", "priv", "owner", "delete", "write", "modify", "update", "prod", "sudo", "grant"
}
FINANCE_KEYWORDS = {
    "fin", "payment", "pay", "invoice", "gl", "sap", "treasury", "settle", "recon"
}
APPROVAL_KEYWORDS = {
    "approve", "approval", "authorise", "authorize", "signoff", "certify"
}


def detect_sod_conflicts(candidate_roles: Iterable[str]) -> List[Dict]:
    """
    candidate_roles: iterable[str]
    Returns list of conflicts found:
      {a, b, severity, reason}
    """
    roles = set(candidate_roles)
    conflicts: List[Dict] = []

    for rule in SOD_RULES:
        a, b = rule["a"], rule["b"]
        if a in roles and b in roles:
            conflicts.append({
                "a": a,
                "b": b,
                "severity": str(rule.get("severity", "MEDIUM")).upper(),
                "reason": str(rule.get("reason", "")),
            })

    conflicts.sort(key=lambda c: SEVERITY_RANK.get(c["severity"], 2), reverse=True)
    return conflicts


def apply_sod_policy(candidate_roles: Iterable[str], block_high: bool = True):
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
                if c["b"] in roles:
                    roles.remove(c["b"])
                    removed.add(c["b"])

    return sorted(roles), sorted(removed), conflicts


def _keyword_flags(role: str) -> Dict[str, bool]:
    r = role.lower()
    return {
        "high_priv": any(k in r for k in HIGH_RISK_KEYWORDS),
        "finance": any(k in r for k in FINANCE_KEYWORDS),
        "approval": any(k in r for k in APPROVAL_KEYWORDS),
    }


def assess_bundle_sod(bundle_roles: Iterable[str]) -> Dict:
    """
    Heuristic SoD assessment for a proposed bundle.

    Output:
      {
        "risk": "LOW|MEDIUM|HIGH",
        "conflicts": [
            { "pair": [a,b], "severity": "...", "rationale": "..." }
        ]
      }

    Logic:
    1) If explicit SOD_RULES conflict exists -> honor that severity
    2) Else heuristic:
       - approval + finance/privileged in same bundle => MEDIUM/HIGH
       - multiple high_priv roles in same bundle => MEDIUM/HIGH
    """
    roles = sorted(set(bundle_roles))
    conflicts: List[Dict] = []

    # 1) Explicit rule matches
    rule_conflicts = detect_sod_conflicts(roles)
    for c in rule_conflicts:
        conflicts.append({
            "pair": [c["a"], c["b"]],
            "severity": c["severity"],
            "rationale": c.get("reason") or "Policy rule conflict",
        })

    # 2) Heuristic pair checks
    flags = {r: _keyword_flags(r) for r in roles}
    for i in range(len(roles)):
        for j in range(i + 1, len(roles)):
            a, b = roles[i], roles[j]
            fa, fb = flags[a], flags[b]

            # Maker-checker style suspicion: approval + finance OR approval + high_priv
            if (fa["approval"] and (fb["finance"] or fb["high_priv"])) or (fb["approval"] and (fa["finance"] or fa["high_priv"])):
                conflicts.append({
                    "pair": [a, b],
                    "severity": "HIGH" if (fa["finance"] or fb["finance"]) else "MEDIUM",
                    "rationale": "Heuristic: approval combined with finance/privileged access (maker-checker risk).",
                })

            # Two privileged-ish roles together
            if fa["high_priv"] and fb["high_priv"]:
                conflicts.append({
                    "pair": [a, b],
                    "severity": "MEDIUM",
                    "rationale": "Heuristic: multiple privileged roles combined in same bundle.",
                })

    # Deduplicate conflicts by (pair,severity,rationale)
    seen = set()
    uniq = []
    for c in conflicts:
        key = (tuple(c["pair"]), c["severity"], c["rationale"])
        if key not in seen:
            uniq.append(c)
            seen.add(key)
    conflicts = uniq

    # Overall risk = max severity observed
    if any(c["severity"] == "HIGH" for c in conflicts):
        risk = "HIGH"
    elif any(c["severity"] == "MEDIUM" for c in conflicts):
        risk = "MEDIUM"
    else:
        risk = "LOW"

    return {"risk": risk, "conflicts": conflicts}
