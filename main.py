import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
import os

app = FastAPI()
DATA_FILE = "valorant_data.json"
GLOBAL_DATA_FILE = "global_data.json"

METRIC_WEIGHTS = {
    'kda': 0.125,
    'kills': 0.125,
    'deaths': 0.125,
    'damage': 0.125,
    'kills_per_round': 0.125,
    'headshots': 0.125,
    'headshots_percent': 0.125,
    'damage_per_round': 0.125
}

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
    rank_parts = rank.lower().strip().replace(" ", "")
    base_rank = ''.join(c for c in rank_parts if c.isalpha())
    tier = ''.join(c for c in rank_parts if c.isdigit())
    formatted_rank = f"{base_rank.capitalize()} {tier}"
    
    for rank_data in global_data.get("ranks", []):
        if rank_data["rank"] == formatted_rank:
            return rank_data
    return {}

def calculate_normalization_constants(matches: List[Dict], metrics: List[str]) -> Dict[str, float]:
    # First normalize each metric to be between 0 and 1
    normalized = {}
    for metric in metrics:
        max_val = max((match[metric] for match in matches), default=0)
        if max_val != 0:
            normalized[metric] = 1 / max_val  
        else:
            normalized[metric] = 0
    

    num_metrics = len(metrics)
    if num_metrics > 0:
        equal_weight = 1.0 / num_metrics
        return {metric: normalized[metric] * equal_weight for metric in metrics}
    return normalized

def calculate_score(performance: Dict, constants: Dict[str, float], metrics: List[str]) -> float:
    score = 0
    for metric in metrics:
        if metric in performance:
            # No need for METRIC_WEIGHTS here since weightage is handled in normalization
            score += performance[metric] * constants[metric]
    return score

def get_rank_tier(rank: str) -> int:
    rank_parts = rank.lower().split()
    base_rank = rank_parts[0]
    
    base_rank_values = {
        'iron': 1,
        'bronze': 4,
        'silver': 7,
        'gold': 10,
        'platinum': 13,
        'diamond': 16,
        'ascendant': 19,
        'immortal': 22,
        'radiant': 25
    }
    
    base_value = base_rank_values.get(base_rank, 0)
    if base_value == 0:
        return 0
        
    if base_rank == 'radiant':
        return base_value
        
    tier = int(rank_parts[1]) if len(rank_parts) > 1 else 1
    return base_value + (tier - 1)

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
    actual_scores = [calculate_score(match, normalization_constants, provided_metrics) for match in matches]
    avg_actual_score = sum(actual_scores) / len(actual_scores) if actual_scores else 0
    predicted_score = calculate_score(bet_request.predicted_performance.dict(), normalization_constants, provided_metrics)
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