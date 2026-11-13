import streamlit as st

from dotenv import load_dotenv

load_dotenv()

from services import api
from services.api import APIError

from views.upload_page import render_upload_page
from views.workflow_page import render_workflow_page


st.set_page_config(
    page_title="Data Quality Inspector",
    page_icon=None,
    layout="wide"
)


# ---------------- SESSION STATE ----------------

defaults = {
    "token": None,
    "user": None,
    "page": "Upload",
    "active_dataset_id": None,
    "active_filename": None,
    "last_upload": None,
    "login_password_visible": False,
    "register_password_visible": False,
    "confirm_password_visible": False
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ---------------- STYLING ----------------

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
            max-width: 1250px;
        }

        div[data-testid="stMetric"] {
            background: #f5f7fa;
            padding: 18px;
            border-radius: 10px;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 10px;
        }

        button[kind="primary"] {
            border-radius: 7px;
        }
    </style>
    """,
    unsafe_allow_html=True
)


# ---------------- PASSWORD INPUT ----------------

def password_input(label, key, visible_key):
    col1, col2 = st.columns([6, 1])

    with col1:
        password = st.text_input(
            label,
            type=(
                "default"
                if st.session_state[visible_key]
                else "password"
            ),
            key=key
        )

    with col2:
        st.write("")

        if st.button(
            "Hide" if st.session_state[visible_key] else "Show",
            key=f"{visible_key}_button"
        ):
            st.session_state[visible_key] = (
                not st.session_state[visible_key]
            )
            st.rerun()

    return password


# ---------------- AUTHENTICATION PAGE ----------------

def render_auth_page():
    st.title("Data Quality Inspector")
    st.write("Sign in to inspect and clean your datasets.")

    auth_mode = st.radio(
        "Authentication",
        ["Login", "Register"],
        horizontal=True
    )

    st.divider()

    if auth_mode == "Login":
        st.subheader("Login")

        email = st.text_input(
            "Email",
            key="login_email"
        )

        password = password_input(
            "Password",
            "login_password",
            "login_password_visible"
        )

        if st.button(
            "Login",
            type="primary",
            use_container_width=True
        ):
            if not email.strip() or not password:
                st.warning("Enter your email and password.")

            else:
                try:
                    with st.spinner("Signing in..."):
                        result = api.login(
                            email.strip(),
                            password
                        )

                        token = result["access_token"]

                        user = api.get_current_user(token)

                    st.session_state.token = token
                    st.session_state.user = user
                    st.session_state.page = "Upload"

                    st.success("Login successful.")
                    st.rerun()

                except APIError as error:
                    st.error(str(error))

    else:
        st.subheader("Create Account")

        full_name = st.text_input(
            "Full Name",
            key="register_full_name"
        )

        email = st.text_input(
            "Email",
            key="register_email"
        )

        password = password_input(
            "Password",
            "register_password",
            "register_password_visible"
        )

        confirm_password = password_input(
            "Confirm Password",
            "confirm_password",
            "confirm_password_visible"
        )

        if st.button(
            "Register",
            type="primary",
            use_container_width=True
        ):
            if not full_name.strip() or not email.strip():
                st.warning("Enter your name and email.")

            elif len(password) < 8:
                st.warning(
                    "Password must contain at least 8 characters."
                )

            elif len(password) > 72:
                st.warning(
                    "Password must not exceed 72 characters."
                )

            elif password != confirm_password:
                st.error("Passwords do not match.")

            else:
                try:
                    with st.spinner("Creating your account..."):
                        api.register(
                            full_name.strip(),
                            email.strip(),
                            password
                        )

                    st.success(
                        "Registration successful. Please log in."
                    )

                except APIError as error:
                    st.error(str(error))


# ---------------- MAIN APPLICATION ----------------

def main():
    token = st.session_state.token

    if not token:
        render_auth_page()
        return

    user = st.session_state.user or {}

    with st.sidebar:
        st.title("Data Quality Inspector")

        st.write(
            user.get("full_name")
            or user.get("email", "User")
        )

        st.divider()

        pages = [
            "Upload",
            "Workflow"
        ]

        if "nav_page" not in st.session_state:
            st.session_state.nav_page = (
                st.session_state.page
                if st.session_state.page in pages
                else "Upload"
            )

        goto = st.session_state.pop("goto_page", None)

        if goto in pages:
            st.session_state.nav_page = goto

        selected_page = st.radio(
            "Navigation",
            pages,
            key="nav_page"
        )

        st.session_state.page = selected_page
        st.divider()

        if st.button(
            "Logout",
            use_container_width=True
        ):
            st.session_state.token = None
            st.session_state.user = None
            st.session_state.active_dataset_id = None
            st.session_state.active_filename = None
            st.session_state.last_upload = None
            st.session_state.page = "Upload"

            st.rerun()

    try:
        if selected_page == "Upload":
            render_upload_page(token)

        elif selected_page == "Workflow":
            render_workflow_page(token)

    except APIError as error:
        st.error(str(error))


if __name__ == "__main__":
    main()