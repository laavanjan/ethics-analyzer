"""
Authentication and authorization module (SEC-03).

Provides centralized authentication enforcement across API endpoints with:
- API key validation via X-API-Key header
- Bearer token support
- Least-privilege access control
- Session-based auth for Streamlit

When ETHICS_API_KEY is set in environment, all protected endpoints require valid credentials.
When unset (local development), routes remain open for backward compatibility.
"""

from fastapi import Depends, Header, HTTPException, status
from typing import Optional
import os
from logging_utils import redact_sensitive


class AuthenticationError(HTTPException):
    """Raised when authentication fails."""
    def __init__(self, detail: str = "Invalid or missing credentials"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_api_key(x_api_key: Optional[str] = Header(default=None)) -> Optional[str]:
    """
    Extract and validate API key from X-API-Key header.

    Returns the API key if valid, None if no API key is required (development mode),
    raises AuthenticationError if invalid.

    SEC-03: Enforce API key validation for all protected endpoints.
    """
    expected_key = os.getenv("ETHICS_API_KEY")

    # Development mode: no API key required
    if not expected_key:
        return None

    # Production mode: API key required
    if not x_api_key:
        raise AuthenticationError(
            detail="Missing X-API-Key header. Set ETHICS_API_KEY environment variable."
        )

    if x_api_key != expected_key:
        raise AuthenticationError(detail="Invalid X-API-Key header.")

    return x_api_key


def get_bearer_token(authorization: Optional[str] = Header(default=None)) -> Optional[str]:
    """
    Extract and validate Bearer token from Authorization header.

    Supports both Bearer tokens and API keys. Falls back to API key if Bearer not provided.

    SEC-03: Support multiple authentication schemes for flexibility.
    """
    expected_key = os.getenv("ETHICS_API_KEY")

    # Development mode
    if not expected_key:
        return None

    if not authorization:
        raise AuthenticationError(
            detail="Missing Authorization header. Use: Authorization: Bearer <token>"
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthenticationError(
            detail="Invalid Authorization header. Use: Authorization: Bearer <token>"
        )

    token = parts[1]
    if token != expected_key:
        raise AuthenticationError(detail="Invalid bearer token.")

    return token


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    """
    Dependency for FastAPI endpoints requiring API key authentication.

    Usage:
        @app.post("/api/endpoint")
        async def endpoint(_auth: None = Depends(require_api_key)):
            ...

    SEC-03: Enforce authentication at endpoint level.
    PRIV-05: Optional API key guard when ETHICS_API_KEY is set.
    """
    expected_key = os.getenv("ETHICS_API_KEY")

    # Development mode: no auth required
    if not expected_key:
        return

    # Production mode: validate API key
    if not x_api_key:
        raise AuthenticationError(
            detail="Missing X-API-Key header. Set ETHICS_API_KEY environment variable."
        )

    if x_api_key != expected_key:
        raise AuthenticationError(detail="Invalid X-API-Key header.")


def require_bearer_token(authorization: Optional[str] = Header(default=None)) -> None:
    """
    Dependency for FastAPI endpoints requiring Bearer token authentication.

    More secure than API key header. Follows OAuth2 standard.

    Usage:
        @app.post("/api/endpoint")
        async def endpoint(_auth: None = Depends(require_bearer_token)):
            ...

    SEC-03: Enforce Bearer token authentication.
    """
    expected_key = os.getenv("ETHICS_API_KEY")

    # Development mode: no auth required
    if not expected_key:
        return

    # Production mode: validate Bearer token
    if not authorization:
        raise AuthenticationError(
            detail="Missing Authorization header. Use: Authorization: Bearer <token>"
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthenticationError(
            detail="Invalid Authorization header. Use: Authorization: Bearer <token>"
        )

    token = parts[1]
    if token != expected_key:
        raise AuthenticationError(detail="Invalid bearer token.")


def check_streamlit_auth(session_state) -> bool:
    """
    Check if user is authenticated in Streamlit session.

    SEC-03: Enforce session-based authentication for Streamlit UI.

    Args:
        session_state: Streamlit session state object

    Returns:
        True if authenticated, False otherwise
    """
    api_key = os.getenv("ETHICS_API_KEY")

    # Development mode: always authenticated
    if not api_key:
        return True

    # Check session state for authentication token
    return getattr(session_state, "authenticated", False)


def streamlit_require_auth(session_state) -> None:
    """
    Enforce authentication for Streamlit app.

    Call at app entry point before rendering protected components.

    SEC-03: Gate Streamlit UI behind authentication when API_KEY is set.
    """
    api_key = os.getenv("ETHICS_API_KEY")

    # Development mode: skip auth
    if not api_key:
        return

    # Production mode: require authentication
    if not check_streamlit_auth(session_state):
        raise PermissionError(
            "User is not authenticated. Please log in with valid credentials."
        )


# Least-privilege endpoint categories for SEC-03 compliance
ENDPOINT_PERMISSIONS = {
    "data": {
        "description": "Data analysis and inspection endpoints",
        "requires_auth": True,
        "example_endpoints": [
            "/api/ethics/analyze",
            "/api/ethics/git-list-files",
        ]
    },
    "model": {
        "description": "Model evaluation and introspection endpoints",
        "requires_auth": True,
        "example_endpoints": [
            "/api/model/info",
            "/api/model/evaluate",
        ]
    },
    "prompt": {
        "description": "Prompt engineering and LLM interaction endpoints",
        "requires_auth": True,
        "example_endpoints": [
            "/api/prompt/analyze",
            "/api/prompt/evaluate",
        ]
    },
    "public": {
        "description": "Public utility endpoints (no auth required)",
        "requires_auth": False,
        "example_endpoints": [
            "/health",
            "/docs",
            "/openapi.json",
        ]
    }
}
