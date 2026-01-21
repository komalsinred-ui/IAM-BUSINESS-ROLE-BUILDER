import streamlit as st
import requests
import pandas as pd

API = "http://127.0.0.1:8000"

def build_filters(supervisor_level6, job_code, department):
    payload = {"supervisor_level6": supervisor_level6.strip()}
    if job_code and job_code.strip():
        payload["job_code"] = job_code.strip()
    if department and department.strip():
        payload["department"] = department.strip()
    return payload


st.set_page_config(page_title="Business Role Builder Dashboard", layout="wide")
st.title("IAM Business Role Builder (Phase 2)")

st.sidebar.header("Filters")
supervisor_level6 = st.sidebar.text_input("Supervisor Level 6", value="SH_L6_1")
job_code = st.sidebar.text_input("Job Code (optional)", value="")
department = st.sidebar.text_input("Department (optional)", value="")

filters = build_filters(supervisor_level6, job_code, department)

st.sidebar.header("Thresholds")
min_group_size = st.sidebar.slider("Min group size", 1, 50, 10)
min_role_support = st.sidebar.slider("Min role support", 0.0, 1.0, 0.6, 0.05)
min_itemset_support = st.sidebar.slider("Min itemset support", 0.0, 1.0, 0.7, 0.05)
max_k = st.sidebar.selectbox("Max bundle size (k)", [2, 3], index=1)

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Bundle Finder",
    "Diagnose (Why empty?)",
    "Role Metrics",
    "User Explain",
    "New Joiner"
])


def clean_optional(v):
    v = v.strip()
    return v if v else None

payload_common = {
    "supervisor_level6": clean_optional(supervisor_level6),
    "job_code": clean_optional(job_code),
    "department": clean_optional(department),
    "min_group_size": min_group_size,
    "min_role_support": float(min_role_support),
    "min_itemset_support": float(min_itemset_support),
    "max_k": int(max_k),
}

with tab1:
    st.subheader("Bundle Suggestions")

    if st.button("Run Bundle Query"):
        payload = {
            **filters,
            "min_group_size": int(min_group_size),
            "min_role_support": float(min_role_support),
            "min_itemset_support": float(min_itemset_support),
            "max_k": int(max_k),
        }

        
        r = requests.post(f"{API}/bundles/query", json=payload, timeout=60)

        # ---- SAFE JSON handling ----
        if r.status_code != 200:
            st.error(f"API error {r.status_code}")
            st.code(r.text)   # shows actual FastAPI error/traceback if any
            st.stop()

        try:
            data = r.json()
        except Exception:
            st.error("API returned non-JSON response")
            st.code(r.text)
            st.stop()

        st.write(f"Returned: {data.get('count', 0)} rows")
        rows = data.get("rows", [])

        if not rows:
            st.warning("No bundles found. Go to Diagnose tab to see why.")
        else:
            df = pd.DataFrame(rows)

            # Clean table (hide nested JSON column)
            display_cols = [c for c in df.columns if c != "sod_conflicts"]
            st.dataframe(df[display_cols], use_container_width=True, hide_index=True)

            st.markdown("### Explainability + SoD (per bundle)")
            for i, row in df.iterrows():
                bundle_roles = row.get("bundle_roles", [])
                tier = row.get("confidence_tier", "NA")
                cov = row.get("coverage_pct", "NA")

                sod_risk = row.get("sod_risk", "NONE")
                sod_count = row.get("sod_conflict_count", 0)

                title = f"Bundle {i+1}: {bundle_roles} ({tier}, {cov}%) | SoD={sod_risk} ({sod_count})"

                with st.expander(title):
                    st.write(row.get("explain", ""))

                    st.markdown("**SoD**")
                    st.write(f"Risk: **{sod_risk}**, Conflicts: **{sod_count}**")

                    conflicts = row.get("sod_conflicts", [])
                    if conflicts:
                        st.json(conflicts)
                    else:
                        st.caption("No SoD conflicts detected for this bundle.")

            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download bundle_suggestions.csv",
                csv,
                file_name="bundle_suggestions.csv",
                mime="text/csv"
            )
          

with tab2:
    st.subheader("Diagnosis Report")
    if st.button("Run Diagnosis"):
        diag_payload = payload_common.copy()
        diag_payload["top_n"] = 10

        r = requests.post(f"{API}/bundles/diagnose", json=diag_payload, timeout=60)
        
        # ---- SAFE JSON handling ----
        if r.status_code != 200:
            st.error(f"API error {r.status_code}")
            st.code(r.text)   # shows actual FastAPI error/traceback if any
            st.stop()

        try:
            report = r.json()
        except Exception:
            st.error("API returned non-JSON response")
            st.code(r.text)
            st.stop()

        st.json(report)

        st.markdown("### Blocking reason")
        st.error(report.get("blocking_reason", "N/A"))

        st.markdown("### Top single roles (approx support)")
        top = report.get("top_single_roles", [])
        if top:
            st.dataframe(pd.DataFrame(top), use_container_width=True)

        st.markdown("### Best pair / triple observed")
        st.write("Best pair support %:", report.get("best_pair_support_pct"))
        st.write("Best triple support %:", report.get("best_triple_support_pct"))

with tab3:
    st.subheader("Role Metrics (Access Ratio Evaluator)")
    if st.button("Load Role Metrics"):
        metrics_payload = {
            "supervisor_level6": clean_optional(supervisor_level6),
            "department": clean_optional(department),
            "job_code": clean_optional(job_code),
            "assignment_type": None
        }
        r = requests.post(f"{API}/roles/metrics", json=metrics_payload, timeout=60)
        # ---- SAFE JSON handling ----
        if r.status_code != 200:
            st.error(f"API error {r.status_code}")
            st.code(r.text)   # shows actual FastAPI error/traceback if any
            st.stop()

        try:
            data = r.json()
        except Exception:
            st.error("API returned non-JSON response")
            st.code(r.text)
            st.stop()

        

        st.write(f"Returned: {data.get('count', 0)} rows")
        rows = data.get("rows", [])
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("Download role_metrics.csv", csv, file_name="role_metrics.csv", mime="text/csv")

with tab4:
    st.subheader("Explain: Why does a user have a role? + Approver")

    # Fetch sample users
    try:
        sample_resp = requests.get(f"{API}/users/sample?n=50", timeout=60)
        sample_resp.raise_for_status()
        sample = sample_resp.json().get("rows", [])
    except Exception as e:
        st.error(f"Failed to load sample users from API: {e}")
        st.stop()

    users = sorted({r.get("user_id") for r in sample if r.get("user_id")})

    if not users:
        st.warning("No users returned from /users/sample")
        st.stop()

    # User selection
    user_id = st.selectbox("User ID", users)

    # Fetch roles for selected user
    roles = []
    try:
        roles_resp = requests.get(f"{API}/users/{user_id}/roles?n=50", timeout=60)
        if roles_resp.status_code == 200:
            roles = roles_resp.json().get("roles", [])
        else:
            st.warning(f"Could not fetch roles for {user_id}. API returned {roles_resp.status_code}.")
    except Exception as e:
        st.warning(f"Could not fetch roles for {user_id}: {e}")

    # Role selector
    if roles:
        role_name = st.selectbox("Role Name", roles)
    else:
        role_name = st.text_input("Role Name", value="AR_CORE_1")

    # Explain button
    if st.button("Explain Access"):
        payload = {"user_id": user_id.strip(), "role_name": role_name.strip()}

        r = requests.post(f"{API}/users/explain-access", json=payload, timeout=60)

         # 1) handle non-200 first
        if r.status_code != 200:
            st.error(f"API error {r.status_code}")
            st.code(r.text)   # show exact backend error (most useful)
            st.stop()

        # 2) now parse JSON safely
        try:
            data = r.json()
        except Exception:
            st.error("API returned non-JSON response")
            st.code(r.text)
            st.stop()

        # 3) render success UI
        st.success(f"Approver: {data.get('approver_level')} | Risk: {data.get('risk')}")

        st.write("**Reasons:**")
        for x in data.get("reasons", []):
            st.write(f"- {x}")

        st.write("**Evidence (coming next):**")
        st.json({
        "user_roles_count": data.get("user_roles_count"),
        "role_prevalence_in_group_pct": data.get("role_prevalence_in_group_pct"),
        "similar_users_count": data.get("similar_users_count"),
        })

        st.write("**User context:**")
        st.json({
        "department": data.get("department"),
        "job_code": data.get("job_code"),
        "supervisor_level6": data.get("supervisor_level6"),
        "assignment_types": data.get("assignment_types"),
        })

with tab5:
    st.subheader("New Joiner Access Recommendation (with SoD policy)")

    nj_job = st.text_input("Job Code", value="JC101")
    nj_sup = st.text_input("Supervisor Level 6 (optional)", value="SH_L6_1")
    nj_dept = st.text_input("Department (optional)", value="")
    nj_support = st.slider("Min role support", 0.0, 1.0, 0.7, 0.05)
    nj_topn = st.slider("Top N roles", 1, 50, 15)
    block_high = st.checkbox("Block HIGH SoD conflicts", value=True)

    if st.button("Recommend Access"):
        payload = {
            "job_code": nj_job.strip(),
            "supervisor_level6": nj_sup.strip() if nj_sup.strip() else None,
            "department": nj_dept.strip() if nj_dept.strip() else None,
            "min_role_support": float(nj_support),
            "top_n": int(nj_topn),
            "block_high_sod": bool(block_high)
        }

        r = requests.post(f"{API}/new-joiner/recommend", json=payload, timeout=60)
        
        if r.status_code != 200:
            st.error(f"API error {r.status_code}")
            st.code(r.text)   # shows actual FastAPI error/traceback if any
            st.stop()

        try:
            data = r.json()
        except Exception:
            st.error("API returned non-JSON response")
            st.code(r.text)
            st.stop()

        st.write(f"Returned: {data.get('count', 0)} rows")
        rows = data.get("rows", [])

        if not rows:
            st.warning("No recommendations found for this cohort. Try lowering min role support.")
        else:
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)

            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("Download new_joiner_recommendation.csv", csv, file_name="new_joiner_recommendation.csv", mime="text/csv")
