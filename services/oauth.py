from observability import setup_observability
from metrics import setup_metrics
import os
import secrets
import hashlib
import base64
from urllib.parse import urlencode

import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse

app = FastAPI(title="OAuth Service")

setup_observability(app, "oauth")

setup_metrics(app)

CLIENT_ID = "homework-client"
REALM = "homework-realm"

KEYCLOAK_PUBLIC = "http://localhost:8081"
KEYCLOAK_INTERNAL = "http://keycloak:8080"
REDIRECT_URI = "http://localhost:8080/oauth/callback"

# Тимчасові OAuth-сесії зберігаємо в Redis
from common import db


def make_challenge(verifier):
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


from typing import Literal


@app.get("/login")
def login(scope_type: Literal["basic", "homework", "users"] = "basic"):
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = make_challenge(verifier)

    db().setex(f"oauth:{state}", 300, verifier)

    scopes = {
        "basic": "openid profile email",
        "homework": "openid profile email homework:read",
        "users": "openid profile email users:write",
    }

    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": scopes[scope_type],
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }

    url = (
        f"{KEYCLOAK_PUBLIC}/realms/{REALM}/protocol/openid-connect/auth?"
        + urlencode(params)
    )

    return RedirectResponse(url)



@app.get("/callback")
def callback(code: str, state: str):
    key = f"oauth:{state}"

    verifier = db().getdel(key)

    if not verifier:
        raise HTTPException(400, "Invalid or expired state")

    token_url = (
        f"{KEYCLOAK_INTERNAL}/realms/{REALM}"
        "/protocol/openid-connect/token"
    )

    response = requests.post(
        token_url,
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        },
        timeout=10,
    )

    if response.status_code != 200:
        raise HTTPException(400, "Token exchange failed")

    # Токени не показуємо на сторінці та не додаємо в URL.
    # Зберігаємо access token у короткоживучій серверній сесії.
    tokens = response.json()
    session_id = secrets.token_urlsafe(32)
    db().setex(f"session:{session_id}", 300, tokens["access_token"])

    result = HTMLResponse(
        "<h2>OAuth 2.0 login successful!</h2>"
        "<p>Authorization Code Flow with PKCE completed.</p>"
    )
    result.set_cookie(
        "oauth_session",
        session_id,
        max_age=300,
        httponly=True,
        secure=False,  # Лише для локального HTTP
        samesite="lax",
    )
    return result


@app.get("/status")
def status(request: Request):
    session_id = request.cookies.get("oauth_session")
    if not session_id:
        raise HTTPException(401, "Not authenticated")

    token = db().get(f"session:{session_id}")
    if not token:
        raise HTTPException(401, "Session expired")

    return {"authenticated": True, "token_present": True}

