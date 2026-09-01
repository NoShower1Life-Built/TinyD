from __future__ import annotations

import os
import re
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import Dial, VoiceResponse

app = FastAPI(title="TinyD Phone Calling API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin for origin in os.getenv("PHONE_ALLOWED_ORIGINS", "http://localhost:8088").split(",") if origin],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Twilio-Signature"],
)
E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def validate_twilio_request(request_url: str, params: dict[str, str], signature: str | None) -> None:
    token = env("TWILIO_AUTH_TOKEN")
    if not signature or not RequestValidator(token).validate(request_url, params, signature):
        raise HTTPException(status_code=403, detail="invalid Twilio signature")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "phone-api"}


@app.get("/token")
def token(identity: str = "user") -> dict[str, str]:
    account_sid = env("TWILIO_ACCOUNT_SID")
    api_key_sid = env("TWILIO_API_KEY_SID")
    api_key_secret = env("TWILIO_API_KEY_SECRET")
    twiml_app_sid = env("TWILIO_TWIML_APP_SID")
    safe_identity = re.sub(r"[^A-Za-z0-9_.-]", "-", identity)[:64] or "user"
    access = AccessToken(account_sid, api_key_sid, api_key_secret, identity=safe_identity, ttl=3600)
    access.add_grant(VoiceGrant(outgoing_application_sid=twiml_app_sid, incoming_allow=True))
    return {"token": access.to_jwt().decode("utf-8"), "identity": safe_identity}


@app.post("/voice")
async def voice(request: Request, x_twilio_signature: str | None = Header(default=None)) -> Response:
    form = await request.form()
    params = {str(k): str(v) for k, v in form.items()}
    validate_twilio_request(str(request.url), params, x_twilio_signature)
    destination = params.get("To", "")
    response = VoiceResponse()
    if not E164.fullmatch(destination):
        response.say("The destination number is invalid.")
        response.hangup()
        return Response(str(response), media_type="application/xml")
    dial = Dial(caller_id=env("TWILIO_CALLER_ID"), answer_on_bridge=True)
    dial.number(destination)
    response.append(dial)
    return Response(str(response), media_type="application/xml")


@app.post("/incoming")
async def incoming(request: Request, x_twilio_signature: str | None = Header(default=None)) -> Response:
    form = await request.form()
    params = {str(k): str(v) for k, v in form.items()}
    validate_twilio_request(str(request.url), params, x_twilio_signature)
    response = VoiceResponse()
    identity = env("DEFAULT_INCOMING_IDENTITY")
    dial = Dial(answer_on_bridge=True)
    dial.client(identity)
    response.append(dial)
    return Response(str(response), media_type="application/xml")


@app.post("/status")
async def status(request: Request, x_twilio_signature: str | None = Header(default=None)) -> Response:
    form = await request.form()
    params = {str(k): str(v) for k, v in form.items()}
    validate_twilio_request(str(request.url), params, x_twilio_signature)
    event = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "call_sid": params.get("CallSid"),
        "status": params.get("CallStatus"),
        "from": params.get("From"),
        "to": params.get("To"),
    }
    print(event, flush=True)
    return Response(status_code=204)
