import random
import pandas as pd


def generate_synthetic_iam_data(
    n_supervisors=5,
    users_per_supervisor=40,
    seed=42
):
    random.seed(seed)

    supervisors = [f"SH_L6_{i}" for i in range(1, n_supervisors + 1)]
    job_codes = ["JC101", "JC102", "JC201", "JC202"]
    assignment_types = ["birthright", "lcm", "batch"]

    core_roles = [f"AR_CORE_{i}" for i in range(1, 8)]
    finance_roles = [f"AR_FIN_{i}" for i in range(1, 6)]
    ops_roles = [f"AR_OPS_{i}" for i in range(1, 6)]
    misc_roles = [f"AR_MISC_{i}" for i in range(1, 10)]

    rows = []

    for sup in supervisors:
        common_bundle = random.sample(core_roles, 3)

        for u in range(1, users_per_supervisor + 1):
            user_id = f"{sup}_U{u:03d}"
            job_code = random.choice(job_codes)
            assignment = random.choice(assignment_types)
            department = "FIN" if job_code.startswith("JC1") else "OPS"

            roles = set()

            # Birthright roles are more consistent
            for r in common_bundle:
                if assignment == "birthright" or random.random() < 0.6:
                    roles.add(r)

            # Job-based roles
            job_bundle = finance_roles if department == "FIN" else ops_roles
            for r in random.sample(job_bundle, 2):
                if random.random() < 0.8:
                    roles.add(r)

            # Noise
            if random.random() < 0.3:
                roles.add(random.choice(misc_roles))

            for role in roles:
                rows.append({
                    "user_id": user_id,
                    "ar_role_name": role,
                    "assignment_type": assignment,
                    "job_code": job_code,
                    "department": department,
                    "supervisor_level6": sup
                })

    return pd.DataFrame(rows)
