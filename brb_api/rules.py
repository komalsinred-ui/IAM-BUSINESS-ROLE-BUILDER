#Approver + “why” rules

# brb_api/rules.py

# Example approver rules (replace with real org rules)
# L1 handles normal apps, L2 handles privileged/high-risk
# brb_api/rules.py

PRIVILEGED_KEYWORDS = {"admin", "write", "delete", "root", "priv", "owner", "fin", "pay", "approve"}


def classify_access_risk(role_name: str) -> str:
    r = (role_name or "").lower()
    return "HIGH" if any(k in r for k in PRIVILEGED_KEYWORDS) else "LOW"

def get_approver(role_name: str) -> str:
    return "L2" if classify_access_risk(role_name) == "HIGH" else "L1"

def _has_birthright(assignment_types) -> bool:
    """
    assignment_types can be:
      - list[str]
      - str (comma-separated or single)
      - None
    """
    if assignment_types is None:
        return False
    if isinstance(assignment_types, list):
        return any(str(x).lower() == "birthright" for x in assignment_types)
    # treat as string
    s = str(assignment_types).lower()
    return "birthright" in s

def explain_why_user_has_role(user_row: dict, role_name: str) -> dict:
    risk = classify_access_risk(role_name)
    approver = get_approver(role_name)

    reasons = []
    if _has_birthright(user_row.get("assignment_types")):
        reasons.append("Birthright / baseline access pattern.")
    if user_row.get("job_code"):
        reasons.append(f"Common for job code: {user_row['job_code']}.")
    if user_row.get("department"):
        reasons.append(f"Common within department: {user_row['department']}.")
    if user_row.get("supervisor_level6"):
        reasons.append(f"Observed within supervisor group: {user_row['supervisor_level6']}.")

    return {
        "risk": risk,
        "approver_level": approver,
        "reasons": reasons if reasons else ["Insufficient metadata to infer a strong reason."],
    }
