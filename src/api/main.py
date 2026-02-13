from fastapi import FastAPI

app = FastAPI(title="EcoShield API", version="0.1.0")

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/")
def root():
    return {"message": "Welcome to EcoShield API"}
