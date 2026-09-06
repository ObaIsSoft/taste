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

    if len(data) < 2:
        return jsonify({"error": "Not enough data"}), 400

    # Find the site that needs rating the most (highest sigma)
    # Filter out ones with no vector if needed, but we should have vectors for all
    data.sort(key=lambda x: x["sigma"], reverse=True)
    site_a = data[0]

    if not site_a.get("vector"):
        # Fallback to a random site if no vector
        site_b = data[1]
    else:
        # Find the most visually similar site that isn't site_a
        best_b = None
        best_sim = -1
        
        # Only look at the top 30 sites that need rating to avoid pairing with a highly confident site
        candidate_pool = [s for s in data[1:31] if s.get("vector")]
        if not candidate_pool:
            candidate_pool = [data[1]]
            
        for candidate in candidate_pool:
            sim = cosine_similarity(site_a["vector"], candidate["vector"])
            if sim > best_sim:
                best_sim = sim
                best_b = candidate
                
        site_b = best_b

    # We shouldn't send the huge vectors to the frontend
    site_a.pop("vector", None)
    site_b.pop("vector", None)

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

    # Fetch current ratings
    res_w = supabase.table("ratings").select("*").eq("site_id", winner_id).execute()
    res_l = supabase.table("ratings").select("*").eq("site_id", loser_id).execute()

    if not res_w.data or not res_l.data:
        return jsonify({"error": "Site not found"}), 404

    winner = res_w.data[0]
    loser = res_l.data[0]

    rating_w = trueskill.Rating(winner["mu"], winner["sigma"])
    rating_l = trueskill.Rating(loser["mu"], loser["sigma"])

    new_rating_w, new_rating_l = trueskill.rate_1vs1(rating_w, rating_l)

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
        "loser_id": loser_id
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
