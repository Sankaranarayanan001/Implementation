import streamlit as st

from services import api
from services.api import APIError


def display_name(value):
    return value.replace("_", " ").title()


def render_upload_page(token):
    st.title("Upload Dataset")
    st.write("Upload an Excel or CSV file to begin data quality analysis.")

    category = "retail_banking"
    purpose = "analytics"

    with st.container(border=True):
        uploaded_file = st.file_uploader(
            "Choose your dataset",
            type=["xlsx", "xls", "xlsm", "csv"]
        )
        if st.button("Upload Dataset", type="primary"):
            if uploaded_file is None:
                st.warning("Please select a file.")
            else:
                try:
                    with st.spinner("Uploading and inspecting dataset..."):
                        result = api.upload_dataset(
                            token=token,
                            filename=uploaded_file.name,
                            file_bytes=uploaded_file.getvalue(),
                            category=category,
                            purpose=purpose
                        )

                    st.session_state.active_dataset_id = result["dataset_id"]
                    st.session_state.active_filename = uploaded_file.name
                    st.session_state.last_upload = result
                    st.session_state.goto_page = "Workflow"

                    st.success("Dataset uploaded successfully.")
                    st.rerun()

                except APIError as error:
                    st.error(str(error))

    st.divider()
    st.subheader("Recent Datasets")

    try:
        datasets = api.list_datasets(token)

        if not datasets:
            st.info("No datasets uploaded yet.")
            return

        for dataset in datasets:
            dataset_id = dataset["id"]
            filename = dataset["filename"]
            status = dataset["status"]
            confirm_key = f"confirm_delete_{dataset_id}"

            with st.container(border=True):
                col1, col2, col3 = st.columns([4, 2, 2])

                with col1:
                    st.markdown(f"**{filename}**")
                    st.caption(
                        f"Category: {display_name(dataset['category'])}"
                    )
                    st.caption(
                        f"Created: {dataset.get('created_at', '-')}"
                    )

                with col2:
                    st.write(f"Status: {display_name(status)}")

                with col3:
                    if st.button(
                        "Open",
                        key=f"open_dataset_{dataset_id}"
                    ):
                        st.session_state.active_dataset_id = dataset_id
                        st.session_state.active_filename = filename
                        st.session_state.goto_page = "Workflow"
                        st.rerun()

                    if status == "cleaned":
                        try:
                            file_bytes = api.download_dataset(
                                token,
                                dataset_id
                            )

                            st.download_button(
                                "Download",
                                data=file_bytes,
                                file_name=f"cleaned_{filename.rsplit('.', 1)[0]}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key=f"download_dataset_{dataset_id}"
                            )

                        except APIError as error:
                            st.caption(str(error))

                    if st.button(
                        "Delete",
                        key=f"delete_dataset_{dataset_id}"
                    ):
                        st.session_state[confirm_key] = True
                        st.rerun()

                if st.session_state.get(confirm_key):
                    st.warning(
                        "Delete this dataset? The uploaded file, cleaned "
                        "Excel and report will be permanently removed. "
                        "This cannot be undone."
                    )

                    yes_col, no_col, _ = st.columns([1, 1, 4])

                    if yes_col.button(
                        "Yes, delete",
                        key=f"confirm_yes_{dataset_id}",
                        type="primary"
                    ):
                        try:
                            api.delete_dataset(token, dataset_id)

                            st.session_state.pop(confirm_key, None)

                            if st.session_state.get("active_dataset_id") == dataset_id:
                                st.session_state.active_dataset_id = None
                                st.session_state.active_filename = None

                            st.rerun()

                        except APIError as error:
                            st.error(str(error))

                    if no_col.button(
                        "Cancel",
                        key=f"confirm_no_{dataset_id}"
                    ):
                        st.session_state.pop(confirm_key, None)
                        st.rerun()

    except APIError as error:
        st.error(str(error))