import time
import uuid
from collections.abc import Callable
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.core.constants import Role
from app.users import supabase_auth
from app.users.models import User

Responses = dict[str, httpx.Response | Exception]
MakeToken = Callable[..., str]

STUDENT_EMAIL = "student@uni.edu"
PROFESSOR_EMAIL = "prof@uni.edu"


@pytest.fixture
def signing_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture(autouse=True)
def trust_test_key(
    monkeypatch: pytest.MonkeyPatch, signing_key: ec.EllipticCurvePrivateKey
) -> None:
    # Stands in for Supabase's JWKS endpoint: the test key is the project's public key.
    class FakeJwksClient:
        def get_signing_key_from_jwt(self, token: str) -> Any:
            return type("SigningKey", (), {"key": signing_key.public_key()})()

    monkeypatch.setattr(security, "jwks_client", FakeJwksClient)


@pytest.fixture(autouse=True)
def professor_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "professor_emails", f" {PROFESSOR_EMAIL.upper()} ")


@pytest.fixture
def make_token(signing_key: ec.EllipticCurvePrivateKey) -> MakeToken:
    def make(
        user_id: uuid.UUID,
        *,
        expires_in: int = 3600,
        audience: str = "authenticated",
        key: Any = None,
        algorithm: str = "ES256",
    ) -> str:
        claims = {
            "sub": str(user_id),
            "aud": audience,
            "iss": f"{get_settings().supabase_url.rstrip('/')}/auth/v1",
            "exp": int(time.time()) + expires_in,
        }
        return jwt.encode(claims, key or signing_key, algorithm=algorithm)

    return make


@pytest.fixture
def supabase(monkeypatch: pytest.MonkeyPatch) -> Responses:
    """Canned Supabase Auth responses, keyed by path and query, such as "/signup"."""
    responses: Responses = {}

    def handle(request: httpx.Request) -> httpx.Response:
        key = request.url.path.removeprefix("/auth/v1")
        if request.url.query:
            key += "?" + request.url.query.decode()
        result = responses[key]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(
        supabase_auth,
        "_client",
        lambda: httpx.Client(
            base_url="https://supabase.test/auth/v1", transport=httpx.MockTransport(handle)
        ),
    )
    return responses


def session_json(
    user_id: uuid.UUID, email: str, access: str = "access-1", refresh: str = "refresh-1"
) -> dict[str, Any]:
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": 3600,
        "token_type": "bearer",
        "user": {"id": str(user_id), "email": email},
    }


def supabase_error(status_code: int, error_code: str, message: str) -> httpx.Response:
    return httpx.Response(
        status_code, json={"code": status_code, "error_code": error_code, "msg": message}
    )


def add_user(db: Session, role: Role, email: str = STUDENT_EMAIL) -> uuid.UUID:
    user = User(id=uuid.uuid4(), email=email, role=role)
    db.add(user)
    db.commit()
    return user.id


def set_cookies(response: httpx.Response) -> dict[str, str]:
    """Set-Cookie headers by cookie name."""
    return {h.split("=", 1)[0]: h for h in response.headers.get_list("set-cookie")}


def assert_session_cookies(response: httpx.Response) -> None:
    cookies = set_cookies(response)
    assert set(cookies) == {"access_token", "refresh_token"}
    for header in cookies.values():
        assert "HttpOnly" in header
        assert "SameSite=lax" in header
        assert "Path=/" in header


def credentials(email: str = STUDENT_EMAIL) -> dict[str, str]:
    return {"email": email, "password": "correct horse"}


# Sign-up


def test_signup_logs_in_a_student_with_httponly_cookies(
    api: TestClient, db_session: Session, supabase: Responses
) -> None:
    user_id = uuid.uuid4()
    supabase["/signup"] = httpx.Response(200, json=session_json(user_id, STUDENT_EMAIL))

    response = api.post("/auth/signup", json=credentials())

    assert response.status_code == 201
    assert response.json() == {
        "user": {"id": str(user_id), "email": STUDENT_EMAIL, "role": "student"},
        "confirm_email": False,
    }
    assert "access-1" not in response.text
    assert "refresh-1" not in response.text
    assert_session_cookies(response)
    assert db_session.get(User, user_id) is not None


def test_signup_with_allowlisted_email_makes_a_professor(
    api: TestClient, supabase: Responses
) -> None:
    supabase["/signup"] = httpx.Response(200, json=session_json(uuid.uuid4(), PROFESSOR_EMAIL))

    response = api.post("/auth/signup", json=credentials(PROFESSOR_EMAIL))

    assert response.json()["user"]["role"] == "professor"


def test_signup_waiting_for_email_confirmation_sets_no_cookies(
    api: TestClient, db_session: Session, supabase: Responses
) -> None:
    supabase["/signup"] = httpx.Response(200, json={"id": str(uuid.uuid4()), "email": "x"})

    response = api.post("/auth/signup", json=credentials())

    assert response.status_code == 201
    assert response.json() == {"user": None, "confirm_email": True}
    assert set_cookies(response) == {}
    assert db_session.query(User).count() == 0


def test_signup_with_a_taken_email_is_a_conflict(api: TestClient, supabase: Responses) -> None:
    supabase["/signup"] = supabase_error(422, "user_already_exists", "User already registered")

    response = api.post("/auth/signup", json=credentials())

    assert response.status_code == 409
    assert response.json()["error"]["message"] == "An account with this email already exists"


def test_signup_rejects_a_short_password_before_calling_supabase(
    api: TestClient, supabase: Responses
) -> None:
    response = api.post("/auth/signup", json={"email": STUDENT_EMAIL, "password": "short"})

    assert response.status_code == 422


# Log-in


def test_login_sets_cookies_and_sets_up_the_account(
    api: TestClient, db_session: Session, supabase: Responses
) -> None:
    user_id = uuid.uuid4()
    supabase["/token?grant_type=password"] = httpx.Response(
        200, json=session_json(user_id, STUDENT_EMAIL)
    )

    response = api.post("/auth/login", json=credentials("Student@Uni.edu"))

    assert response.status_code == 200
    assert response.json() == {"id": str(user_id), "email": STUDENT_EMAIL, "role": "student"}
    assert_session_cookies(response)
    assert db_session.get(User, user_id) is not None


def test_login_promotes_a_student_added_to_the_allowlist(
    api: TestClient, db_session: Session, supabase: Responses
) -> None:
    user_id = add_user(db_session, Role.STUDENT, PROFESSOR_EMAIL)
    supabase["/token?grant_type=password"] = httpx.Response(
        200, json=session_json(user_id, PROFESSOR_EMAIL)
    )

    response = api.post("/auth/login", json=credentials(PROFESSOR_EMAIL))

    assert response.json()["role"] == "professor"


def test_login_relinks_an_account_recreated_in_supabase(
    api: TestClient, db_session: Session, supabase: Responses
) -> None:
    old_id = add_user(db_session, Role.PROFESSOR, PROFESSOR_EMAIL)
    new_id = uuid.uuid4()
    supabase["/token?grant_type=password"] = httpx.Response(
        200, json=session_json(new_id, PROFESSOR_EMAIL)
    )

    response = api.post("/auth/login", json=credentials(PROFESSOR_EMAIL))

    assert response.status_code == 200
    assert response.json() == {"id": str(new_id), "email": PROFESSOR_EMAIL, "role": "professor"}
    db_session.expire_all()
    assert db_session.get(User, old_id) is None
    assert db_session.query(User).count() == 1


@pytest.mark.parametrize(
    ("error_code", "status_code", "message"),
    [
        (
            "invalid_credentials",
            401,
            "That email and password don't match. Check them and try again.",
        ),
        ("email_not_confirmed", 403, "Confirm your email before logging in"),
    ],
)
def test_login_failures_have_clear_messages(
    api: TestClient, supabase: Responses, error_code: str, status_code: int, message: str
) -> None:
    supabase["/token?grant_type=password"] = supabase_error(400, error_code, "nope")

    response = api.post("/auth/login", json=credentials())

    assert response.status_code == status_code
    assert response.json()["error"]["message"] == message
    assert set_cookies(response) == {}


def test_login_when_supabase_is_down_is_unavailable(api: TestClient, supabase: Responses) -> None:
    supabase["/token?grant_type=password"] = httpx.ConnectError("down")

    response = api.post("/auth/login", json=credentials())

    assert response.status_code == 503


# The token check


def test_me_returns_the_signed_in_user(
    api: TestClient, db_session: Session, make_token: MakeToken
) -> None:
    user_id = add_user(db_session, Role.STUDENT)
    api.cookies.set("access_token", make_token(user_id))

    response = api.get("/auth/me")

    assert response.status_code == 200
    assert response.json() == {"id": str(user_id), "email": STUDENT_EMAIL, "role": "student"}


def test_me_without_a_cookie_is_unauthorized(api: TestClient) -> None:
    response = api.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Not logged in"


def test_expired_token_says_the_session_expired(
    api: TestClient, db_session: Session, make_token: MakeToken
) -> None:
    api.cookies.set("access_token", make_token(add_user(db_session, Role.STUDENT), expires_in=-60))

    response = api.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Session expired"


@pytest.mark.parametrize(
    "token_options",
    [
        pytest.param({"key": ec.generate_private_key(ec.SECP256R1())}, id="wrong-signature"),
        pytest.param({"audience": "anon"}, id="wrong-audience"),
        pytest.param({"key": "a-shared-secret-of-32-bytes-long", "algorithm": "HS256"}, id="hs256"),
    ],
)
def test_untrusted_tokens_are_rejected(
    api: TestClient, db_session: Session, make_token: MakeToken, token_options: dict[str, Any]
) -> None:
    api.cookies.set("access_token", make_token(add_user(db_session, Role.STUDENT), **token_options))

    response = api.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid session"


def test_token_for_an_account_not_set_up_is_unauthorized(
    api: TestClient, make_token: MakeToken
) -> None:
    api.cookies.set("access_token", make_token(uuid.uuid4()))

    response = api.get("/auth/me")

    assert response.status_code == 401


@pytest.mark.parametrize(("role", "expected"), [(Role.STUDENT, 403), (Role.PROFESSOR, 201)])
def test_professor_routes_check_the_stored_role(
    api: TestClient, db_session: Session, make_token: MakeToken, role: Role, expected: int
) -> None:
    api.cookies.set("access_token", make_token(add_user(db_session, role)))

    response = api.post("/courses", json={"title": "Intro to Programming"})

    assert response.status_code == expected


# Refresh and log-out


def test_refresh_rotates_both_cookies(
    api: TestClient, db_session: Session, supabase: Responses
) -> None:
    user_id = add_user(db_session, Role.STUDENT)
    supabase["/token?grant_type=refresh_token"] = httpx.Response(
        200, json=session_json(user_id, STUDENT_EMAIL, access="access-2", refresh="refresh-2")
    )
    api.cookies.set("refresh_token", "refresh-1")

    response = api.post("/auth/refresh")

    assert response.status_code == 200
    cookies = set_cookies(response)
    assert cookies["access_token"].startswith("access_token=access-2;")
    assert cookies["refresh_token"].startswith("refresh_token=refresh-2;")


def test_refresh_without_a_cookie_is_unauthorized(api: TestClient) -> None:
    response = api.post("/auth/refresh")

    assert response.status_code == 401


@pytest.mark.parametrize(
    "error_code", ["refresh_token_already_used", "refresh_token_not_found", "validation_failed"]
)
def test_refresh_with_a_rejected_token_asks_to_log_in_again(
    api: TestClient, supabase: Responses, error_code: str
) -> None:
    supabase["/token?grant_type=refresh_token"] = supabase_error(400, error_code, "Invalid")
    api.cookies.set("refresh_token", "refresh-1")

    response = api.post("/auth/refresh")

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Session expired. Log in again"


@pytest.mark.parametrize(
    "supabase_result",
    [httpx.Response(204), httpx.Response(500), httpx.ConnectError("down")],
    ids=["revoked", "supabase-error", "supabase-down"],
)
def test_logout_always_clears_the_cookies(
    api: TestClient, supabase: Responses, supabase_result: httpx.Response | Exception
) -> None:
    supabase["/logout?scope=local"] = supabase_result
    api.cookies.set("access_token", "access-1")

    response = api.post("/auth/logout")

    assert response.status_code == 204
    cookies = set_cookies(response)
    assert set(cookies) == {"access_token", "refresh_token"}
    assert all("Max-Age=0" in header for header in cookies.values())


# Forgot and reset password


@pytest.mark.parametrize(
    "supabase_result",
    [httpx.Response(200, json={}), supabase_error(400, "user_not_found", "User not found")],
    ids=["account-exists", "no-such-account"],
)
def test_forgot_password_never_says_whether_the_account_exists(
    api: TestClient, supabase: Responses, supabase_result: httpx.Response
) -> None:
    supabase["/recover"] = supabase_result

    response = api.post("/auth/forgot-password", json={"email": STUDENT_EMAIL})

    assert response.status_code == 204


def test_forgot_password_passes_on_rate_limits(api: TestClient, supabase: Responses) -> None:
    supabase["/recover"] = supabase_error(429, "over_email_send_rate_limit", "Too many emails")

    response = api.post("/auth/forgot-password", json={"email": STUDENT_EMAIL})

    assert response.status_code == 429


def test_reset_password_sets_the_password_and_logs_in(
    api: TestClient, db_session: Session, supabase: Responses, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = add_user(db_session, Role.STUDENT)
    supabase["/verify"] = httpx.Response(200, json=session_json(user_id, STUDENT_EMAIL))
    supabase["/user"] = httpx.Response(200, json={"id": str(user_id)})
    sent: list[httpx.Request] = []
    real_client = supabase_auth._client

    def recording_client() -> httpx.Client:
        client = real_client()
        client.event_hooks["request"].append(sent.append)
        return client

    monkeypatch.setattr(supabase_auth, "_client", recording_client)

    response = api.post(
        "/auth/reset-password", json={"token_hash": "hash-1", "password": "new password"}
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(user_id)
    assert_session_cookies(response)
    update = next(request for request in sent if request.url.path.endswith("/user"))
    assert update.method == "PUT"
    assert update.headers["Authorization"] == "Bearer access-1"


def test_reset_password_with_a_used_link_asks_for_a_new_one(
    api: TestClient, supabase: Responses
) -> None:
    supabase["/verify"] = supabase_error(403, "otp_expired", "Token has expired or is invalid")

    response = api.post(
        "/auth/reset-password", json={"token_hash": "hash-1", "password": "new password"}
    )

    assert response.status_code == 400
    assert response.json()["error"]["message"] == (
        "This reset link has expired or was already used. Request a new one."
    )
    assert set_cookies(response) == {}


def test_reset_password_rejects_a_short_password_before_using_the_link(
    api: TestClient, supabase: Responses
) -> None:
    response = api.post("/auth/reset-password", json={"token_hash": "hash-1", "password": "short"})

    assert response.status_code == 422
    assert "/verify" not in supabase
