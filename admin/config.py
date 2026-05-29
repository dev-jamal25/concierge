import os


def default_api_base_url() -> str:
    return os.getenv("ADMIN_API_BASE_URL", "http://localhost:8000").rstrip("/")


def public_api_base_url() -> str:
    return os.getenv("ADMIN_PUBLIC_API_BASE_URL", "http://localhost:8000").rstrip("/")
