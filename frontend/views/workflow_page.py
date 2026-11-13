
import streamlit as st
import pandas as pd

from services import api
from services.api import APIError


# ---------------- CUSTOM STYLING ----------------

st.markdown("""
<style>
[data-testid="stMetricLabel"],
[data-testid="stMetricLabel"] p {
    color: #374151 !important;
}

[data-testid="stMetricValue"],
[data-testid="stMetricValue"] div,
[data-testid="stMetricValue"] p {
    color: #111827 !important;
}

[data-testid="stMetricDelta"] {
    color: #374151 !important;
}
</style>
""", unsafe_allow_html=True)


# ---------------- HELPERS ----------------

def display_name(value):
    return str(value).replace("_", " ").title()


# ---------------- RECOMMENDATION SELECTION CALLBACK ----------------

def update_recommendation_selection(dataset_id, rec_id):
    selection_key = f"selected_recommendations_{dataset_id}"
    checkbox_key = f"select_{dataset_id}_{rec_id}"

    selected = st.session_state[selection_key]

    if st.session_state.get(checkbox_key, False):
        selected.add(rec_id)
    else:
        selected.discard(rec_id)

def set_filtered_selection(dataset_id, rec_ids, value):
    selection_key = f"selected_recommendations_{dataset_id}"

    for rec_id in rec_ids:
        st.session_state[f"select_{dataset_id}_{rec_id}"] = value

        if value:
            st.session_state[selection_key].add(rec_id)
        else:
            st.session_state[selection_key].discard(rec_id)

# ---------------- COLUMN MAPPING ----------------

def render_mapping(token, dataset_id, detail):
    st.subheader("Column Mapping")

    suggestions = detail.get("suggested_mappings") or []
    fields = detail.get("available_banking_fields") or []

    if not suggestions:
        st.warning(
            "Mapping suggestions are unavailable. Check the backend "
            "dataset detail endpoint configuration."
        )
        return

    st.write(
        "Review the suggested mapping for each column. "
        "Choose Not mapped when no banking field applies."
    )

    mappings = {}

    for index, item in enumerate(suggestions):
        column_name = item.get("column")
        suggested = item.get("suggested")
        samples = item.get("samples", [])
        source = item.get("source", "-")

        if not column_name:
            continue

        widget_key = f"mapping_{dataset_id}_{index}"

        select_options = ["Not mapped"] + fields

        if widget_key not in st.session_state:
            if suggested in fields:
                st.session_state[widget_key] = suggested
            else:
                st.session_state[widget_key] = "Not mapped"

        with st.container(border=True):
            col1, col2 = st.columns([2, 3])

            with col1:
                st.markdown(f"**{column_name}**")
                st.caption(f"Suggestion source: {source}")

                if samples:
                    st.caption("Samples: " + ", ".join(samples))

            with col2:
                selected = st.selectbox(
                    "Map to banking field",
                    options=select_options,
                    key=widget_key
                )

                mappings[column_name] = (
                    None if selected == "Not mapped" else selected
                )

    selected_fields = [
        value for value in mappings.values()
        if value is not None
    ]

    duplicates = sorted({
        value for value in selected_fields
        if selected_fields.count(value) > 1
    })

    if duplicates:
        st.error(
            "A banking field cannot be assigned to multiple columns: "
            + ", ".join(duplicates)
        )

    if st.button(
        "Confirm Mapping",
        type="primary",
        disabled=bool(duplicates) or not selected_fields
    ):
        try:
            with st.spinner("Saving column mappings..."):
                api.confirm_mappings(
                    token,
                    dataset_id,
                    mappings
                )

            st.success("Column mappings confirmed.")
            st.rerun()

        except APIError as error:
            st.error(str(error))


# ---------------- DATASET ANALYSIS ----------------

def render_analysis(token, dataset_id):
    st.subheader("Dataset Analysis")

    try:
        result = api.get_results(token, dataset_id)

        summary = result.get("summary", {})
        issues = result.get("issues", [])

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Total Issues",
            summary.get("total_issues", 0)
        )

        col2.metric(
            "Rule Engine Issues",
            summary.get("rule_engine_issues", 0)
        )

        col3.metric(
            "AI Verified Issues",
            summary.get("ai_verified_new_issues", 0)
        )

        st.markdown("**Detected Issues**")

        issue_rows = []

        for issue in issues:
            issue_rows.append({
                "Issue ID": issue.get("id"),
                "Column": issue.get("column") or "Dataset",
                "Issue Type": display_name(
                    issue.get("issue_type", "")
                ),
                "Severity": display_name(
                    issue.get("severity", "")
                ),
                "Affected Rows": issue.get("affected_rows", 0)
            })

        if issue_rows:
            st.dataframe(
                pd.DataFrame(issue_rows),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No issues detected.")

    except APIError as error:
        st.error(str(error))


# ---------------- CLEANING RECOMMENDATIONS ----------------

def render_recommendations(token, dataset_id):
    st.subheader("Cleaning Recommendations")

    try:
        result = api.get_recommendations(
            token,
            dataset_id
        )

        recommendations = result.get("recommendations", [])

        if not recommendations:
            st.info("No recommendations available.")
            return

        st.write(
            "Select the cleaning actions you want to approve."
        )

        # Initialize persistent selection storage
        selection_key = f"selected_recommendations_{dataset_id}"

        if selection_key not in st.session_state:
            st.session_state[selection_key] = set()

        # Get unique cleaning actions from backend
        solution_types = sorted({
            rec.get("action")
            for rec in recommendations
            if rec.get("action")
        })

        filter_options = ["All Solutions"] + solution_types

        # Cleaning solution dropdown
        selected_filter = st.selectbox(
            "Filter by Cleaning Solution",
            options=filter_options,
            format_func=lambda x: (
                x if x == "All Solutions" else display_name(x)
            ),
            key=f"solution_filter_{dataset_id}"
        )

        # Filter recommendations
        if selected_filter == "All Solutions":
            filtered_recommendations = recommendations
        else:
            filtered_recommendations = [
                rec for rec in recommendations
                if rec.get("action") == selected_filter
            ]

        st.caption(
            f"Showing {len(filtered_recommendations)} of "
            f"{len(recommendations)} recommendations"
        )
        filtered_ids = [
            rec.get("id") for rec in filtered_recommendations
            if rec.get("id")
        ]

        btn_col1, btn_col2, _ = st.columns([2, 2, 4])

        btn_col1.button(
            f"Select all shown ({len(filtered_ids)})",
            key=f"select_all_{dataset_id}_{selected_filter}",
            on_click=set_filtered_selection,
            args=(dataset_id, filtered_ids, True),
            type="secondary"
        )

        btn_col2.button(
            "Clear shown",
            key=f"clear_all_{dataset_id}_{selected_filter}",
            on_click=set_filtered_selection,
            args=(dataset_id, filtered_ids, False)
        )

        # Display filtered recommendation cards
        for recommendation in filtered_recommendations:

            rec_id = recommendation.get("id")
            column = recommendation.get("column") or "Dataset"

            issue_type = display_name(
                recommendation.get("issue_type", "")
            )

            action = display_name(
                recommendation.get("action", "")
            )

            affected_rows = recommendation.get(
                "affected_rows", 0
            )

            checkbox_key = f"select_{dataset_id}_{rec_id}"

            # Restore selection when switching filters
            if checkbox_key not in st.session_state:
                st.session_state[checkbox_key] = (
                    rec_id in st.session_state[selection_key]
                )

            with st.container(border=True):

                col1, col2, col3, col4 = st.columns(
                    [1, 2, 2, 2]
                )

                with col1:
                    st.checkbox(
                        "Select",
                        key=checkbox_key,
                        label_visibility="collapsed",
                        on_change=update_recommendation_selection,
                        args=(dataset_id, rec_id)
                    )

                with col2:
                    st.markdown(f"**{column}**")
                    st.caption(rec_id)

                with col3:
                    st.write(issue_type)
                    st.caption(
                        f"Affected rows: {affected_rows}"
                    )

                with col4:
                    st.write(action)

        # Collect selections from ALL recommendations
        selected_recommendations = [
            {
                "rec_id": rec_id,
                "decision": "approve"
            }
            for rec_id in st.session_state[selection_key]
        ]

        st.write(
            f"Selected recommendations: "
            f"{len(selected_recommendations)}"
        )

        if st.button(
            "Submit Review",
            type="primary",
            disabled=not selected_recommendations
        ):
            try:
                with st.spinner("Submitting your review..."):

                    api.submit_review(
                        token,
                        dataset_id,
                        selected_recommendations
                    )

                # Clear selections after successful submission
                st.session_state[selection_key] = set()

                st.success("Review submitted successfully.")
                st.rerun()

            except APIError as error:
                st.error(str(error))

    except APIError as error:
        st.error(str(error))


# ---------------- CLEANING RESULTS ----------------

def render_cleaning_result(token, dataset_id, detail):
    st.subheader("Cleaning Results")

    post_validation = detail.get("post_validation") or {}

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Rows Before",
        post_validation.get("rows_before", 0)
    )

    col2.metric(
        "Rows After",
        post_validation.get("rows_after", 0)
    )

    col3.metric(
        "Issues Before",
        post_validation.get("issues_before", 0)
    )

    col4.metric(
        "Issues After",
        post_validation.get("issues_after", 0)
    )

    cleaning_log = detail.get("cleaning_log") or []

    if cleaning_log:
        st.markdown("**Applied Cleaning Actions**")

        rows = []

        for item in cleaning_log:
            rows.append({
                "Recommendation": item.get("rec_id"),
                "Column": item.get("column"),
                "Action": display_name(item.get("action", "")),
                "Status": display_name(item.get("status", "")),
                "Affected Rows": item.get("affected_rows", 0)
            })

        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True
        )

    try:
        excel_bytes = api.download_dataset(
            token,
            dataset_id
        )

        st.download_button(
            "Download Cleaned Excel",
            data=excel_bytes,
            file_name=f"cleaned_dataset_{dataset_id}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )

        report_html = api.get_report(
            token,
            dataset_id
        )

        st.download_button(
            "Download HTML Report",
            data=report_html,
            file_name=f"data_quality_report_{dataset_id}.html",
            mime="text/html"
        )

        st.divider()
        st.subheader("Report Preview")

        # Streamlit HTML preview
        st.html(report_html)

    except APIError as error:
        st.error(str(error))


# ---------------- MAIN WORKFLOW ----------------

def render_workflow_page(token):

    dataset_id = st.session_state.get("active_dataset_id")

    st.title("Data Cleaning Workflow")

    if not dataset_id:
        st.info(
            "Upload a dataset or open one from Recent Datasets."
        )
        return

    try:
        detail = api.get_dataset(
            token,
            dataset_id
        )

        filename = detail.get("filename", "Dataset")
        status = detail.get("status", "uploaded")

        st.markdown(f"**Dataset:** {filename}")
        st.caption(
            f"Current status: {display_name(status)}"
        )

        st.divider()

        # Step 1: Column Mapping
        if status == "uploaded":

            render_mapping(
                token,
                dataset_id,
                detail
            )

        # Step 2: Dataset Analysis
        elif status == "mapped":

            st.subheader("Ready for Analysis")

            st.write(
                "Column mapping has been confirmed. "
                "You can now analyze the dataset."
            )

            if st.button(
                "Analyze Dataset",
                type="primary"
            ):

                try:
                    with st.spinner(
                        "Analyzing dataset and detecting quality issues..."
                    ):

                        api.analyze_dataset(
                            token,
                            dataset_id
                        )

                    st.success("Dataset analysis completed.")
                    st.rerun()

                except APIError as error:
                    st.error(str(error))

        # Step 3: Generate Recommendations
        elif status == "analyzed":

            render_analysis(
                token,
                dataset_id
            )

            st.divider()

            if st.button(
                "Generate Recommendations",
                type="primary"
            ):

                try:
                    with st.spinner(
                        "Generating cleaning recommendations..."
                    ):

                        api.generate_recommendations(
                            token,
                            dataset_id
                        )

                    st.success("Recommendations generated.")
                    st.rerun()

                except APIError as error:
                    st.error(str(error))

        # Step 4: Recommendation Review
        elif status == "recommended":

            render_recommendations(
                token,
                dataset_id
            )

         # Step 5: Cleaning Execution
        elif status == "reviewed":

            st.subheader("Review Completed")

            st.success(
                "Your recommendation decisions have been saved."
            )

            st.write(
                "The approved cleaning actions will be applied with the "
                "Python cleaning engine, then the cleaned data will be "
                "validated again."
            )

            if st.button(
                "Clean Dataset",
                type="primary"
            ):

                try:
                    with st.spinner(
                        "Applying cleaning actions and validating cleaned data..."
                    ):

                        api.clean_dataset(
                            token,
                            dataset_id
                        )

                    st.success("Dataset cleaned successfully.")
                    st.rerun()

                except APIError as error:
                    st.error(str(error))

        # Step 6: Cleaning Results
        elif status == "cleaned":

            render_cleaning_result(
                token,
                dataset_id,
                detail
            )

        else:

            st.warning(
                f"Unknown dataset status: {status}"
            )

    except APIError as error:
        st.error(str(error))
