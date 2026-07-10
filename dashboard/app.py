from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from dashboard.approval_store import REJECT_REASONS, export_rejection_summary, load_approvals, log_dashboard, save_approval
from dashboard.components import suggestion_detail, suggestion_table_rows
from dashboard.data_loader import (
    account_status_rows,
    account_comparison_chart_data,
    automation_readiness,
    approval_chart_data,
    dashboard_summary,
    filter_suggestions,
    latest_preview_path,
    load_preview,
    overall_summary,
    rule_feedback,
    trend_chart_data,
)


st.set_page_config(page_title="Meta Automation Dashboard", layout="wide")


def main() -> None:
    log_dashboard("dashboard_started", {})
    st.title("Meta Automation Dashboard")
    page = st.sidebar.radio("Navigation", ["Home", "Budget Review", "Rule Feedback"])
    preview_path = latest_preview_path()
    preview = load_preview(preview_path)
    if not preview.run_id:
        st.warning("No Budget Manager Preview JSON found. Run python main.py --budget-manager-preview first.")
        return
    log_dashboard("preview_loaded", {"run_id": preview.run_id, "suggestions": len(preview.suggestions)})
    st.sidebar.caption(f"RUN_ID: {preview.run_id}")
    st.sidebar.caption(f"Preview: {preview.path}")

    if page == "Home":
        render_home(preview)
    elif page == "Budget Review":
        render_review(preview)
    else:
        render_feedback(preview.run_id)


def render_home(preview) -> None:
    st.subheader("1. Overview")
    overall = overall_summary(preview)
    cols = st.columns(5)
    cols[0].metric("Overall Account Status", overall["overall_status"])
    cols[1].metric("Overall 3D ROAS", overall["overall_3d_roas"])
    cols[2].metric("Overall Today ROAS", overall["overall_today_roas"])
    cols[3].metric("Overall Spend", overall["overall_spend"])
    cols[4].metric("Overall Purchase", overall["overall_purchase"])
    st.metric("Overall Data Confidence", overall["overall_data_confidence"])

    st.subheader("2. Account Status")
    rows = list(account_status_rows(preview).values())
    st.dataframe(rows, use_container_width=True, hide_index=True)

    st.subheader("3. Today's Review Summary")
    summary = dashboard_summary(preview)
    cols = st.columns(7)
    cols[0].metric("Suggestions", summary["total"])
    cols[1].metric("Pending", summary["pending"])
    cols[2].metric("Approved", summary["approved"])
    cols[3].metric("Rejected", summary["rejected"])
    cols[4].metric("High Risk", summary["high_risk"])
    cols[5].metric("Data Insufficient", summary["data_insufficient"])
    cols[6].metric("Data Error", summary["data_error"])
    if st.button("View Review Queue", type="primary"):
        st.session_state["go_review"] = True
        st.rerun()

    st.subheader("4. Charts")
    metric = st.selectbox("Trend Metric", ["Spend", "ROAS"])
    st.line_chart(trend_chart_data(preview, metric))
    performance_data, brand_data = account_comparison_chart_data(preview)
    st.caption("Performance Account Comparison")
    st.bar_chart(performance_data, x="Account", y=["Spend", "ROAS"])
    st.caption("Brand Account Comparison")
    st.bar_chart(brand_data, x="Account", y=["Spend", "CTR", "CPM"])
    st.caption("Review Status")
    st.bar_chart(approval_chart_data(preview))


def render_review(preview) -> None:
    st.subheader("Budget Review Queue")
    decision = st.selectbox("Decision", ["ALL", "PENDING", "APPROVED", "REJECTED", "SKIPPED"])
    account_options = {"ALL": "ALL", **{item.account_name: item.account_id for item in preview.suggestions}}
    account_label = st.selectbox("Account", list(account_options.keys()))
    action = st.selectbox("Suggestion Type", ["ALL"] + sorted({item.proposed_action for item in preview.suggestions}))
    risk = st.selectbox("Risk Level", ["ALL", "LOW", "MEDIUM", "HIGH"])
    rows = filter_suggestions(preview.suggestions, decision=decision, account_id=account_options[account_label], action=action, risk=risk)
    st.dataframe(suggestion_table_rows(rows), use_container_width=True, hide_index=True)

    st.subheader("Review Items")
    for item in rows:
        title = f"{item.risk_level} | {item.account_name} | {item.proposed_action} | {item.campaign_name or item.adset_name}"
        with st.expander(title):
            st.json(suggestion_detail(item), expanded=False)
            reviewer = st.text_input("Reviewer", value="Ruobing Li", key=f"reviewer_{item.review_id}")
            reject_reason = st.selectbox("Reject Reason", [""] + REJECT_REASONS, key=f"reason_{item.review_id}")
            reject_note = st.text_area("Reject Note", key=f"note_{item.review_id}")
            cols = st.columns(3)
            if cols[0].button("Approve", key=f"approve_{item.review_id}", disabled=item.risk_level == "HIGH"):
                save_approval(item, "APPROVED", reviewer=reviewer)
                st.success("Approved. This did not execute any Meta budget change.")
                st.rerun()
            if cols[1].button("Reject", key=f"reject_{item.review_id}"):
                if not reject_reason:
                    st.error("Reject requires a reason.")
                else:
                    save_approval(item, "REJECTED", reject_reason=reject_reason, reject_note=reject_note, reviewer=reviewer)
                    st.success("Rejected.")
                    st.rerun()
            if cols[2].button("Skip", key=f"skip_{item.review_id}"):
                save_approval(item, "SKIPPED", reject_note=reject_note, reviewer=reviewer)
                st.success("Skipped.")
                st.rerun()

    st.subheader("Batch Operations")
    batch_reason = st.selectbox("Batch Reject Reason", REJECT_REASONS, key="batch_reason")
    batch_note = st.text_area("Batch Note", key="batch_note")
    if st.button("Batch Reject Filtered Items"):
        for item in rows:
            save_approval(item, "REJECTED", reject_reason=batch_reason, reject_note=batch_note)
        st.success(f"Rejected {len(rows)} items.")
        st.rerun()
    if st.button("Batch Skip Filtered Items"):
        for item in rows:
            save_approval(item, "SKIPPED", reject_note=batch_note)
        st.success(f"Skipped {len(rows)} items.")
        st.rerun()


def render_feedback(run_id: str) -> None:
    st.subheader("Rule Feedback")
    records = list(load_approvals(run_id).values())
    feedback = rule_feedback(records)
    cols = st.columns(6)
    cols[0].metric("Total Suggestions", feedback["total"])
    cols[1].metric("Approved", feedback["approved"])
    cols[2].metric("Rejected", feedback["rejected"])
    cols[3].metric("Skipped", feedback["skipped"])
    cols[4].metric("Approval Rate", f"{feedback['approval_rate']:.0%}")
    cols[5].metric("Reject Rate", f"{feedback['reject_rate']:.0%}")
    st.metric("Automation Readiness", automation_readiness(records))
    st.subheader("Top Reject Reasons")
    reason_rows = [{"Reason": reason, "Count": count} for reason, count in feedback["reject_reasons"]]
    st.dataframe(reason_rows, use_container_width=True, hide_index=True)
    if st.button("Export Rejection Summary"):
        path = export_rejection_summary(records)
        st.success(f"Exported to {path}")


if __name__ == "__main__":
    main()
