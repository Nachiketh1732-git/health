from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
import analytics

app = FastAPI(
    title="Health Analytics API",
    description="Backend service for health metrics and analytics calculation.",
    version="1.0.0",
)

# Enable CORS so your frontend (React/Vercel) can talk to this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows requests from any origin
    allow_credentials=True,
    allow_methods=["*"],  # Allows GET, POST, PUT, DELETE, etc.
    allow_headers=["*"],
)

# Pydantic data model for incoming requests
class HealthDataInput(BaseModel):
    user_id: Optional[str] = "demo_user"
    steps: Optional[int] = 8000
    sleep_hours: Optional[float] = 7.5
    heart_rate: Optional[int] = 72
    metrics: Optional[Dict[str, Any]] = None


@app.get("/")
def read_root():
    return {
        "status": "online",
        "message": "Health Analytics API is live!",
        "documentation": "/docs",
    }


@app.get("/api/health-check")
def health_check():
    return {"status": "healthy", "service": "health-backend"}


@app.post("/api/analytics/calculate")
def analyze_health_data(data: HealthDataInput):
    try:
        input_dict = data.model_dump()

        # Connect functions from analytics.py dynamically
        if hasattr(analytics, "process_health_data"):
            result = analytics.process_health_data(input_dict)
        elif hasattr(analytics, "calculate_score"):
            result = analytics.calculate_score(input_dict)
        else:
            # Fallback output showing inputs are successfully parsed
            result = {
                "summary": "Data received successfully.",
                "raw_input": input_dict,
                "status": "Ready to attach custom analytics functions.",
            }

        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
