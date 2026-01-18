from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import pandas as pd
import os

from brb_api.schemas import (
    BundleQueryRequest, NewJoinerRequest,
    GenericFilterRequest, ExportCSVRequest, BundleDiagnoseRequest
)
from brb_api.services import (
    load_data, query_bundles, get_role_metrics, get_user_summary,
    new_joiner, diagnose_bundles
)

DATA_PATH = "data/synthetic_iam_extract.csv"

app = FastAPI(title="BRB API", version="0.1")


def load_df():
    return pd.read_csv(DATA_PATH)


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- USERS (supporting endpoints used by Streamlit) ----------
@app.get("/users/sample")
def sample_users(n: int = 10):
    df = load_df()
    cols = [c for c in ["user_id", "supervisor_level6", "job_code", "department", "assignment_type", "ar_role_name"]
            if c in df.columns]
    return {"rows": df[cols].drop_duplicates().head(n).to_dict(orient="records")}


@app.get("/users/{user_id}/roles")
def get_user_roles(user_id: str, n: int = 25):
    df = load_df()
    udf = df[df["user_id"] == user_id]
    if udf.empty:
        raise HTTPException(status_code=404, detail="user not found")
    roles = sorted(udf["ar_role_name"].unique().tolist())
    return {"user_id": user_id, "roles": roles[:n], "count": len(roles)}


class ExplainAccessReq(BaseModel):
    user_id: str
    role_name: str



@app.post("/users/explain-access")
def explain_access(req: ExplainAccessReq):
    df = load_df()

    if "ar_role_name" not in df.columns:
        raise HTTPException(status_code=500, detail="Dataset missing 'ar_role_name' column")

    user_id = req.user_id.strip()
    role_name = req.role_name.strip()

    udf = df[df["user_id"] == user_id]
    if udf.empty:
        raise HTTPException(status_code=404, detail=f"user_id {user_id} not found")

    # Ensure the user actually has this role
    if udf[udf["ar_role_name"] == role_name].empty:
        sample_roles = sorted(udf["ar_role_name"].unique().tolist())[:15]
        raise HTTPException(
            status_code=400,
            detail=f"user {user_id} does not have role {role_name}. sample_roles={sample_roles}"
        )

    def safe_first(col):
        return udf[col].dropna().iloc[0] if col in udf.columns and udf[col].dropna().size > 0 else None

    supervisor_level6 = safe_first("supervisor_level6")
    job_code = safe_first("job_code")
    department = safe_first("department")

    assignment_types = (
        sorted(udf["assignment_type"].dropna().unique().tolist())
        if "assignment_type" in udf.columns else []
    )

    # ---- Evidence group: supervisor_level6 + job_code ----
    if supervisor_level6 is None or job_code is None:
        # If missing metadata, we can’t compute prevalence reliably
        peer_df = pd.DataFrame()
        group_users_total = 0
        role_users_in_group = 0
        role_prev_pct = None
        similar_users_count = 0
        sample_peer_user_ids = []
    else:
        peer_df = df[
            (df["supervisor_level6"] == supervisor_level6) &
            (df["job_code"] == job_code)
        ]

        group_users = peer_df["user_id"].dropna().unique().tolist()
        group_users_total = len(group_users)

        # users in peer group who have the role
        role_users = peer_df.loc[peer_df["ar_role_name"] == role_name, "user_id"].dropna().unique().tolist()
        role_users_in_group = len(role_users)

        role_prev_pct = round((role_users_in_group / group_users_total) * 100, 2) if group_users_total > 0 else 0.0
        similar_users_count = group_users_total
        sample_peer_user_ids = sorted(group_users)[:10]

    # User role count
    user_roles_count = udf["ar_role_name"].dropna().nunique()

    # ---- Reasons (simple demo logic) ----
    reasons = []
    atypes_lower = {x.lower() for x in assignment_types}
    if "birthright" in atypes_lower:
        reasons.append("Role is likely Birthright (assigned broadly to this cohort).")
    if job_code:
        reasons.append(f"User job_code={job_code} suggests job-based access pattern.")
    if department:
        reasons.append(f"User department={department} provides business context (may be cross-functional).")

    if role_prev_pct is not None:
        reasons.append(
            f"In peer group (supervisor_level6={supervisor_level6}, job_code={job_code}), "
            f"{role_users_in_group}/{group_users_total} users have this role ({role_prev_pct}%)."
        )

    reasons.append(f"User has role {role_name} in source extract (synthetic IAM dataset).")

    # ---- Approver + Risk heuristic (demo) ----
    r_upper = role_name.upper()
    if "ADMIN" in r_upper or "FIN" in r_upper or "WRITE" in r_upper:
        approver = "L2"
        risk = "MEDIUM"
    else:
        approver = "L1"
        risk = "LOW"

    return {
        "user_id": user_id,
        "role_name": role_name,
        "approver_level": approver,
        "risk": risk,
        "reasons": reasons,

        # context
        "department": department,
        "job_code": job_code,
        "supervisor_level6": supervisor_level6,
        "assignment_types": assignment_types,

        # evidence
        "user_roles_count": int(user_roles_count),
        "role_prevalence_in_group_pct": role_prev_pct,
        "role_users_in_group": int(role_users_in_group),
        "group_users_total": int(group_users_total),
        "similar_users_count": int(similar_users_count),
        "sample_peer_user_ids": sample_peer_user_ids,
    }



# ---------- CORE API ----------
@app.post("/bundles/query")
def bundles_query(req: BundleQueryRequest):
    df = load_data()
    out = query_bundles(df, req)
    return {"rows": out.to_dict(orient="records"), "count": len(out)}


@app.post("/roles/metrics")
def roles_metrics(req: GenericFilterRequest):
    df = load_data()
    out = get_role_metrics(df, req)
    return {"rows": out.to_dict(orient="records"), "count": len(out)}


@app.post("/users/summary")
def users_summary(req: GenericFilterRequest):
    df = load_data()
    out = get_user_summary(df, req)
    return {"rows": out.to_dict(orient="records"), "count": len(out)}


@app.post("/new-joiner/recommend")
def new_joiner_recommend(req: NewJoinerRequest):
    df = load_data()
    out = new_joiner(df, req)
    return {"rows": out.to_dict(orient="records"), "count": len(out)}


@app.post("/bundles/diagnose")
def bundles_diagnose(req: BundleDiagnoseRequest):
    df = load_data()
    return diagnose_bundles(df, req)


@app.post("/export/csv")
def export_csv(req: ExportCSVRequest):
    os.makedirs("outputs", exist_ok=True)
    path = os.path.join("outputs", req.filename)
    pd.DataFrame(req.rows).to_csv(path, index=False)
    return {"saved_to": path, "rows": len(req.rows)}
