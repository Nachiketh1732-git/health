from fastapi import FastAPI
import analytics

app = FastAPI(title="Health Analytics API")

@app.get("/")
def read_root():
    return {"message": "Health Analytics API is live!"}
