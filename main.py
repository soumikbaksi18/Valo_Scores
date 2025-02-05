import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
import os

app = FastAPI()
DATA_FILE = "valorant_data.json"
GLOBAL_DATA_FILE = "global_data.json"

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

def load_data(file_path: str):
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def get_user_rank(userId: str) -> Optional[str]:
    data = load_data(DATA_FILE)
    if data.get("username") == userId:
        return data.get("rank")
    return None

def fetch_rank_averages(rank: str) -> Dict[str, float]:
    global_data = load_data(GLOBAL_DATA_FILE)
    for rank_data in global_data.get("ranks", []):
        if rank_data["rank"].lower() == rank.lower():
            return rank_data
    return {}

def calculate_normalization_constants(matches: List[Dict], metrics: List[str]) -> Dict[str, float]:
    return {metric: 1 / max(match[metric] for match in matches) if max(match[metric] for match in matches) != 0 else 0 
            for metric in metrics}

def calculate_score(performance: Dict, constants: Dict[str, float], metrics: List[str], stake: int) -> float:
    score = 0
    for metric in metrics:
        if metric in performance:
            weightage = max(0.1, 1 - (stake / (performance[metric] + 1))) 
            score += performance[metric] * constants[metric] * weightage
    return score

def get_rank_tier(rank: str) -> int:
    rank_tiers = {
        'iron': 1,
        'bronze': 2,
        'silver': 3,
        'gold': 4,
        'platinum': 5,
        'diamond': 6,
        'ascendant': 7,
        'immortal': 8,
        'radiant': 9
    }
    return rank_tiers.get(rank.lower(), 0)

def adjust_score_with_ai(predicted_score: float, user_avg_score: float, rank_averages: Dict[str, float], 
                        provided_metrics: List[str], user_rank: str) -> float:
    # Get rank tier for scaling
    rank_tier = get_rank_tier(user_rank)
    if rank_tier == 0:
        return predicted_score
    
    # Base adjustment starts at 1.0
    adjustment_factor = 1.0
    
    for metric in provided_metrics:
        if metric in rank_averages and user_avg_score > 0:
            deviation = (predicted_score / user_avg_score) - 1
            
            rank_scaling = 1 + (rank_tier / 10)  
            
            if deviation > 0:
                adjustment_factor *= (1 - (deviation * 0.2 * rank_scaling))
            else:
                adjustment_factor *= (1 + (abs(deviation) * 0.1 * rank_scaling))
            
            adjustment_factor = max(0.5, min(1.5, adjustment_factor))
    
    return predicted_score * adjustment_factor

@app.post("/calculate-performance")
async def calculate_performance(bet_request: BetRequest):
    data = load_data(DATA_FILE)
    user_rank = get_user_rank(bet_request.userId)
    
    if not user_rank:
        raise HTTPException(status_code=404, detail=f"No rank found for user {bet_request.userId}")
    
    matches = [m for m in data.get('matchResults', []) if m['name'] == bet_request.userId]
    if not matches:
        raise HTTPException(status_code=404, detail=f"No match history found for user {bet_request.userId}")
    
    rank_averages = fetch_rank_averages(user_rank)
    if not rank_averages:
        raise HTTPException(status_code=404, detail=f"No global data found for rank {user_rank}")
    
    provided_metrics = [metric for metric, value in bet_request.predicted_performance.dict().items() if value is not None]
    normalization_constants = calculate_normalization_constants(matches, provided_metrics)
    actual_scores = [calculate_score(match, normalization_constants, provided_metrics, bet_request.stake) for match in matches]
    avg_actual_score = sum(actual_scores) / len(actual_scores) if actual_scores else 0
    predicted_score = calculate_score(bet_request.predicted_performance.dict(), normalization_constants, provided_metrics, bet_request.stake)
    adjusted_predicted_score = adjust_score_with_ai(predicted_score, avg_actual_score, rank_averages, provided_metrics, user_rank)
    odd_percentage = (adjusted_predicted_score / avg_actual_score) * 100 if avg_actual_score != 0 else 0
    
    return {
        "userId": bet_request.userId,
        "rank": user_rank,
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