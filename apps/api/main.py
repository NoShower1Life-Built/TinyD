from fastapi import FastAPI

app = FastAPI(title="TinyD API", version="1.0")


@app.get("/health")
def health():
    return {"status": "ok", "service": "tinyd-api"}
