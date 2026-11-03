# TinyD Phone

A real browser VoIP phone for outbound and inbound PSTN calls. The client uses the Twilio Voice JavaScript SDK; the backend creates short-lived Voice access tokens and returns TwiML for call routing. TinyD remains outside the real-time media path.

## Components

- `backend/app.py` — FastAPI token and TwiML endpoints.
- `frontend/` — React/Vite phone client.
- `backend/Dockerfile` — non-root backend container.

## Provider setup

Create a Twilio account, purchase/verify a voice-capable phone number, create an API key, and create a TwiML Application. Configure the TwiML application's Voice URL as `POST https://YOUR_HOST/voice`, status callback as `POST https://YOUR_HOST/status`, and configure the purchased number's incoming Voice URL as `POST https://YOUR_HOST/incoming`.

Set the variables in `.env.example`. `TWILIO_AUTH_TOKEN` and `TWILIO_API_KEY_SECRET` are server-only secrets and must never be exposed to the browser.

The browser sends E.164 destinations such as `+15551234567`. The backend rejects malformed destinations before producing `<Dial>` instructions.

## Run backend

```bash
cd apps/phone/backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8080
```

## Run frontend

```bash
cd apps/phone/frontend
npm install
VITE_PHONE_API=http://localhost:8080 npm run dev
```

For browser microphone access outside localhost, serve the frontend over HTTPS. The Twilio Voice SDK uses secure signaling and DTLS-SRTP media.

## Production requirements

Use HTTPS, authenticate `/token` against the application's real user/session identity, persist call events in the canonical TinyD event ledger, add rate/fraud controls, restrict allowed destination countries, and configure CSP/security headers. Do not store Twilio secrets in source control.

This first implementation intentionally does not fake call state, audio, carrier connectivity, or provider responses. A real PSTN call requires valid provider resources and credentials.
