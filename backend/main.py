from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Nexora Architect API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok", "service": "nexora-architect"}

@app.get("/projects")
def list_projects():
    return {
        "projects": ["TinyD", "VCIR", "Æther", "SOC Platform", "Aetheris"]
    }

@app.post("/analyze")
def analyze(payload: dict):
    return {
        "analysis": "stub",
        "input": payload
    }
