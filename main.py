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
    stake: Optional[int] = 15 

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

def calculate_score(performance: Dict, constants: Dict[str, float], metrics: List[str], stake: int) -> float:
    score = 0
    for metric in metrics:
        if metric in performance:
            weightage = max(0.1, 1 - (stake / (performance[metric] + 1))) 
            score += performance[metric] * constants[metric] * weightage
    return score

# Dummy global averages
def fetch_global_averages() -> Dict[str, float]:
    return {
        "kda": 2,
        "kills": 15,
        "deaths": 10,
        "damage": 2500,
        "kills_per_round": 0.5,
        "headshots": 2,
        "headshots_percent": 18.0,
        "damage_per_round": 120.0
    }

def adjust_score_with_ai(predicted_score: float, user_avg_score: float, global_averages: Dict[str, float], provided_metrics: List[str]) -> float:
    adjustment_factor = 1.0
    for metric in provided_metrics:
        if metric in global_averages:
            if user_avg_score > global_averages[metric]:
                adjustment_factor *= 0.8  
    
    return predicted_score * adjustment_factor

@app.post("/calculate-performance")
async def calculate_performance(bet_request: BetRequest):
    data = load_data()
    
    matches = [m for m in data.get('matchResults', []) if m['name'] == bet_request.userId]
    
    if not matches:
        raise HTTPException(status_code=404, detail=f"No match history found for user {bet_request.userId}")
    
    provided_metrics = [metric for metric, value in bet_request.predicted_performance.dict().items() if value is not None]
    
    normalization_constants = calculate_normalization_constants(matches, provided_metrics)
    actual_scores = [calculate_score(match, normalization_constants, provided_metrics, bet_request.stake) for match in matches]
    avg_actual_score = sum(actual_scores) / len(actual_scores) if actual_scores else 0
    predicted_score = calculate_score(bet_request.predicted_performance.dict(), normalization_constants, provided_metrics, bet_request.stake)
    
    global_averages = fetch_global_averages()
    
    adjusted_predicted_score = adjust_score_with_ai(predicted_score, avg_actual_score, global_averages, provided_metrics)
    
    odd_percentage = (adjusted_predicted_score / avg_actual_score) * 100 if avg_actual_score != 0 else 0
    
    return {
        "userId": bet_request.userId,
        "predicted_score": round(predicted_score, 2),
        "adjusted_predicted_score": round(adjusted_predicted_score, 2),
        "performance_score": round(avg_actual_score, 2),
        "odd_percentage": round(odd_percentage, 2)
    }

class UserRequest(BaseModel):
    userId: str

# @app.post("/average-performance")
# async def average_performance(request: UserRequest):
#     data = load_data()
#     matches = [match for match in data.get("matchResults", []) if match["name"] == request.userId]

#     if not matches:
#         raise HTTPException(status_code=404, detail=f"No match history found for user {request.userId}")

#     metrics = [
#         "kda", "kills", "deaths", "damage",
#         "kills_per_round", "headshots",
#         "headshots_percent", "damage_per_round"
#     ]

#     # Compute averages for the specific user
#     total_matches = len(matches)
#     averages = {metric: sum(match[metric] for match in matches) / total_matches for metric in metrics}

#     return {
#         "userId": request.userId,
#         "total_matches": total_matches,
#         "average_performance": {metric: round(avg, 2) for metric, avg in averages.items()}
#     }