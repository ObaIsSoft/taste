from flask import Flask, request, jsonify
import os
import json
import numpy as np
from supabase import create_client, Client
import trueskill

app = Flask(__name__)

# Initialize TrueSkill
trueskill.setup(mu=25.0, sigma=8.333, beta=4.167, tau=0.0833, draw_probability=0.0)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase = None

def cosine_similarity(v1, v2):
    v1 = np.array(v1)
    v2 = np.array(v2)
    return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-9)

@app.route("/api/ping", methods=["GET"])
def ping():
    return jsonify({"status": "ok"})

@app.route("/api/next_pair", methods=["GET"])
def next_pair():
    if not supabase:
        return jsonify({"error": "Supabase not configured"}), 500

    # Fetch all ratings
    res = supabase.table("ratings").select("*").execute()
    data = res.data

    import random

    if len(data) < 2:
        return jsonify({"error": "Not enough data"}), 400

    # Dynamic Voting Ender: If the dataset has reached an average of 15 comparisons per site,
    # the algorithm has mathematically stabilized. This dynamically scales if new sites are added.
    avg_comparisons = sum(d["comparisons"] for d in data) / len(data)
    if avg_comparisons >= 15:
        return jsonify({"status": "complete"})

    # Sort by highest sigma (most uncertain)
    data.sort(key=lambda x: x["sigma"], reverse=True)
    
    # Pick randomly from the top 5 most uncertain sites to prevent immediate rematches
    top_uncertain = data[:5]
    site_a = random.choice(top_uncertain)

    if not site_a.get("vector"):
        # Fallback to a random site if no vector
        available = [d for d in data if d["site_id"] != site_a["site_id"]]
        site_b = random.choice(available) if available else data[0]
    else:
        # Find visually similar sites
        candidate_pool = [s for s in data if s.get("vector") and s["site_id"] != site_a["site_id"]]
        if not candidate_pool:
            candidate_pool = [d for d in data if d["site_id"] != site_a["site_id"]]
            
        # Calculate similarity for all candidates
        for candidate in candidate_pool:
            if candidate.get("vector"):
                candidate["_sim"] = cosine_similarity(site_a["vector"], candidate["vector"])
            else:
                candidate["_sim"] = -1
                
        candidate_pool.sort(key=lambda x: x.get("_sim", -1), reverse=True)
        
        # Pick randomly from the top 5 most similar to ensure variety
        top_similar = candidate_pool[:5]
        site_b = random.choice(top_similar)

    # We shouldn't send the huge vectors to the frontend
    site_a.pop("vector", None)
    site_b.pop("vector", None)
    site_a.pop("_sim", None)
    site_b.pop("_sim", None)

    return jsonify({"site_a": site_a, "site_b": site_b})

@app.route("/api/vote", methods=["POST"])
def vote():
    if not supabase:
        return jsonify({"error": "Supabase not configured"}), 500

    body = request.json
    winner_id = body.get("winner_id")
    loser_id = body.get("loser_id")

    if not winner_id or not loser_id:
        return jsonify({"error": "Missing winner_id or loser_id"}), 400

    is_draw = body.get("is_draw", False)

    # Fetch current ratings
    res_w = supabase.table("ratings").select("*").eq("site_id", winner_id).execute()
    res_l = supabase.table("ratings").select("*").eq("site_id", loser_id).execute()

    if not res_w.data or not res_l.data:
        return jsonify({"error": "Site not found"}), 404

    winner = res_w.data[0]
    loser = res_l.data[0]

    rating_w = trueskill.Rating(winner["mu"], winner["sigma"])
    rating_l = trueskill.Rating(loser["mu"], loser["sigma"])

    new_rating_w, new_rating_l = trueskill.rate_1vs1(rating_w, rating_l, drawn=is_draw)

    if is_draw:
        # Update winner (treating as draw)
        supabase.table("ratings").update({
            "mu": new_rating_w.mu,
            "sigma": new_rating_w.sigma,
            "comparisons": winner["comparisons"] + 1
        }).eq("site_id", winner_id).execute()

        # Update loser (treating as draw)
        supabase.table("ratings").update({
            "mu": new_rating_l.mu,
            "sigma": new_rating_l.sigma,
            "comparisons": loser["comparisons"] + 1
        }).eq("site_id", loser_id).execute()

        # Record match
        supabase.table("match_history").insert({
            "winner_id": winner_id,
            "loser_id": loser_id,
            "is_draw": True
        }).execute()
    else:
        # Update winner
        supabase.table("ratings").update({
            "mu": new_rating_w.mu,
            "sigma": new_rating_w.sigma,
            "wins": winner["wins"] + 1,
            "comparisons": winner["comparisons"] + 1
        }).eq("site_id", winner_id).execute()
    
        # Update loser
        supabase.table("ratings").update({
            "mu": new_rating_l.mu,
            "sigma": new_rating_l.sigma,
            "losses": loser["losses"] + 1,
            "comparisons": loser["comparisons"] + 1
        }).eq("site_id", loser_id).execute()
    
        # Record match
        supabase.table("match_history").insert({
            "winner_id": winner_id,
            "loser_id": loser_id,
            "is_draw": False
        }).execute()

    return jsonify({"status": "success"})

@app.route("/api/leaderboard", methods=["GET"])
def leaderboard():
    if not supabase:
        return jsonify({"error": "Supabase not configured"}), 500

    res = supabase.table("ratings").select("site_id, mu, sigma, wins, losses, comparisons").execute()
    data = res.data

    # Conservative score: mu - 3*sigma
    for site in data:
        site["score"] = site["mu"] - 3 * site["sigma"]

    data.sort(key=lambda x: x["score"], reverse=True)
    return jsonify({"leaderboard": data})

if __name__ == "__main__":
    app.run(port=5000)
