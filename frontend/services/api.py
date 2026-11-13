import os
import requests

from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000" 
).rstrip("/")


class APIError(Exception):
    pass


def api_call(method, endpoint, token=None, **kwargs):
    headers = kwargs.pop("headers", {})

    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.request(
            method=method,
            url=f"{BASE_URL}{endpoint}",
            headers=headers,
            timeout=180,
            **kwargs
        )

    except requests.RequestException as error:
        raise APIError(f"Cannot connect to backend: {error}")

    if not response.ok:
        try:
            data = response.json()
            message = data.get("detail", response.text)
        except ValueError:
            message = response.text

        raise APIError(
            f"Backend error ({response.status_code}): {message}"
        )

    return response


# ---------------- AUTH ----------------

def register(full_name, email, password):
    response = api_call(
        "POST",
        "/auth/register",
        json={
            "full_name": full_name,
            "email": email,
            "password": password
        }
    )

    return response.json()


def login(email, password):
    response = api_call(
        "POST",
        "/auth/login",
        data={
            "username": email,
            "password": password
        }
    )

    return response.json()


def get_current_user(token):
    response = api_call(
        "GET",
        "/auth/me",
        token=token
    )

    return response.json()


# ---------------- OPTIONS ----------------

def get_options(token):
    response = api_call(
        "GET",
        "/datasets/options",
        token=token
    )

    return response.json()


# ---------------- DATASETS ----------------

def list_datasets(token):
    response = api_call(
        "GET",
        "/datasets",
        token=token
    )

    return response.json()


def upload_dataset(token, filename, file_bytes, category, purpose):
    response = api_call(
        "POST",
        "/datasets/upload",
        token=token,
        files={
            "file": (
                filename,
                file_bytes
            )
        },
        data={
            "category": category,
            "purpose": purpose
        }
    )

    return response.json()


def get_dataset(token, dataset_id):
    response = api_call(
        "GET",
        f"/datasets/{dataset_id}",
        token=token
    )

    return response.json()


# ---------------- COLUMN MAPPING ----------------

def confirm_mappings(token, dataset_id, mappings):
    response = api_call(
        "POST",
        f"/datasets/{dataset_id}/mappings/confirm",
        token=token,
        json={
            "mappings": mappings
        }
    )

    return response.json()


# ---------------- ANALYSIS ----------------

def analyze_dataset(token, dataset_id):
    response = api_call(
        "POST",
        f"/datasets/{dataset_id}/analyze",
        token=token
    )

    return response.json()


def get_results(token, dataset_id):
    response = api_call(
        "GET",
        f"/datasets/{dataset_id}/results",
        token=token
    )

    return response.json()


# ---------------- RECOMMENDATIONS ----------------

def generate_recommendations(token, dataset_id):
    response = api_call(
        "POST",
        f"/datasets/{dataset_id}/recommendations",
        token=token
    )

    return response.json()


def get_recommendations(token, dataset_id):
    response = api_call(
        "GET",
        f"/datasets/{dataset_id}/recommendations",
        token=token
    )

    return response.json()


# ---------------- REVIEW ----------------

def submit_review(token, dataset_id, decisions):
    response = api_call(
        "POST",
        f"/datasets/{dataset_id}/review",
        token=token,
        json={
            "decisions": decisions,
            "approve_all_pending": False
        }
    )

    return response.json()


# ---------------- CLEANING ----------------

def clean_dataset(token, dataset_id):
    response = api_call(
        "POST",
        f"/datasets/{dataset_id}/clean",
        token=token
    )

    return response.json()


# ---------------- DOWNLOAD ----------------

def download_dataset(token, dataset_id):
    response = api_call(
        "GET",
        f"/datasets/{dataset_id}/download",
        token=token
    )

    return response.content


def get_report(token, dataset_id):
    response = api_call(
        "GET",
        f"/datasets/{dataset_id}/report",
        token=token
    )

    return response.text

def delete_dataset(token, dataset_id):
    r = requests.delete(
        f"{BASE_URL}/datasets/{dataset_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    if r.status_code >= 400:
        raise Exception(f"Backend error ({r.status_code}): {r.text}")
    return r.json()