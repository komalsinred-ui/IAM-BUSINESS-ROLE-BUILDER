from brb_core.synthetic_data import generate_synthetic_iam_data
from brb_core.bundling import suggest_itemsets
from brb_core.metrics import role_usage_metrics, user_access_summary, role_overlap_jaccard
from brb_core.new_joiner import recommend_access_for_new_joiner

def main():
    df = generate_synthetic_iam_data()
    print(df.head())
    print("Total rows:", len(df))

    df.to_csv("data/synthetic_iam_extract.csv", index=False)
    print("Saved synthetic dataset to data/synthetic_iam_extract.csv")

    # 1) Bundle suggestions (pairs + triples)
    bundles = suggest_itemsets(
        df,
        group_cols=("supervisor_level6", "job_code"),
        min_role_support=0.60,
        min_itemset_support=0.70,
        max_k=3,
        min_group_size=10
    )
    bundles.to_csv("outputs/bundle_suggestions.csv", index=False)
    print("Saved bundle suggestions to outputs/bundle_suggestions.csv")
    print("Total bundle suggestions:", len(bundles))

    # 2) Access Ratio Evaluator (role usage metrics)
    metrics = role_usage_metrics(df, group_cols=("department",))
    metrics.to_csv("outputs/role_metrics.csv", index=False)
    print("Saved role metrics to outputs/role_metrics.csv")

    # Optional: per-user summary (useful for chatbot later)
    users = user_access_summary(df)
    users.to_csv("outputs/user_access_summary.csv", index=False)
    print("Saved user access summary to outputs/user_access_summary.csv")

    # Optional: overlap (top overlaps)
    overlap = role_overlap_jaccard(df, min_common_users=5, top_n=50)
    overlap.to_csv("outputs/role_overlap_top50.csv", index=False)
    print("Saved role overlap to outputs/role_overlap_top50.csv")

        # New Joiner Recommendation (example cohort)
    sample_job = df["job_code"].iloc[0]
    sample_sup = df["supervisor_level6"].iloc[0]

    rec = recommend_access_for_new_joiner(
        df,
        job_code=sample_job,
        supervisor_level6=sample_sup,
        min_role_support=0.70,
        top_n=15
    )
    rec.to_csv("outputs/new_joiner_recommendation.csv", index=False)
    print("Saved new joiner recommendation to outputs/new_joiner_recommendation.csv")



if __name__ == "__main__":
    main()
