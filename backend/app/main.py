from fastapi import FastAPI

app = FastAPI(
    title="Kpinder API",
    description="Dating service MVP API",
    version="0.1.0",
)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
