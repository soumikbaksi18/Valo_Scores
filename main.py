import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
import os

app = FastAPI()
DATA_FILE = "valorant_data.json"

class MatchPerformance(BaseModel):
    kda: Optional[float] = None
    kills: Optional[int] = None
    deaths: Optional[int] = None
    damage: Optional[int] = None
    kills_per_round: Optional[float] = None
    headshots: Optional[int] = None
    headshots_percent: Optional[float] = None
    damage_per_round: Optional[float] = None

class BetRequest(BaseModel):
    userId: str
    predicted_performance: MatchPerformance

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def calculate_normalization_constants(matches: List[Dict], metrics: List[str]) -> Dict[str, float]:
    return {metric: 1/max(match[metric] for match in matches) if max(match[metric] for match in matches) != 0 else 0 
            for metric in metrics}

def calculate_score(performance: Dict, constants: Dict[str, float], metrics: List[str]) -> float:
    return sum(performance[metric] * constants[metric] for metric in metrics if metric in performance)

@app.post("/calculate-performance")
async def calculate_performance(bet_request: BetRequest):
    data = load_data()
    
    matches = [m for m in data.get('matchResults', []) if m['name'] == bet_request.userId]
    
    if not matches:
        raise HTTPException(status_code=404, detail=f"No match history found for user {bet_request.userId}")
    
    # Get the metrics that are provided in the predicted_performance
    provided_metrics = [metric for metric, value in bet_request.predicted_performance.dict().items() if value is not None]
    
    normalization_constants = calculate_normalization_constants(matches, provided_metrics)
    actual_scores = [calculate_score(match, normalization_constants, provided_metrics) for match in matches]
    avg_actual_score = sum(actual_scores) / len(actual_scores) if actual_scores else 0
    predicted_score = calculate_score(bet_request.predicted_performance.dict(), normalization_constants, provided_metrics)
    
    odd_percentage = (predicted_score / avg_actual_score) * 100 if avg_actual_score != 0 else 0
    
    return {
        "userId": bet_request.userId,
        "predicted_score": round(predicted_score, 2),
        "performance_score": round(avg_actual_score, 2),
        "odd_percentage": round(odd_percentage, 2)
    }

class UserRequest(BaseModel):
    userId: str

@app.post("/average-performance")
async def average_performance(request: UserRequest):
    data = load_data()
    matches = [match for match in data.get("matchResults", []) if match["name"] == request.userId]

    if not matches:
        raise HTTPException(status_code=404, detail=f"No match history found for user {request.userId}")

    metrics = [
        "kda", "kills", "deaths", "damage",
        "kills_per_round", "headshots",
        "headshots_percent", "damage_per_round"
    ]

    # Compute averages for the specific user
    total_matches = len(matches)
    averages = {metric: sum(match[metric] for match in matches) / total_matches for metric in metrics}

    return {
        "userId": request.userId,
        "total_matches": total_matches,
        "average_performance": {metric: round(avg, 2) for metric, avg in averages.items()}
    }