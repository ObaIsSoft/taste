from flask import Flask, request, jsonify
import os
import json
import numpy as np
from supabase import create_client, Client
import trueskill
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder="../public", static_url_path="/")

@app.route("/")
def serve_index():
    return app.send_static_file("index.html")

@app.route("/guide.html")
def serve_guide():
    return app.send_static_file("guide.html")

@app.route("/README.md")
def serve_readme():
    return app.send_static_file("README.md")

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
    voter_id = body.get("voter_id")
    if voter_id:
        voter_id = voter_id.strip().lower().replace(" ", "_")
    reasoning = body.get("reasoning", "").strip()

    if not winner_id or not loser_id:
        return jsonify({"error": "Missing winner_id or loser_id"}), 400

    # Validate reasoning (required for non-draw votes)
    is_draw = body.get("is_draw", False)
    if not is_draw and voter_id and len(reasoning) < 10:
        return jsonify({"error": "Reasoning required (min 10 characters)"}), 400

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
            "is_draw": True,
            "voter_id": voter_id,
            "reasoning": reasoning if reasoning else None
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
            "is_draw": False,
            "voter_id": voter_id,
            "reasoning": reasoning if reasoning else None
        }).execute()

    # Update voter stats
    if voter_id:
        _update_voter_stats(voter_id)

    return jsonify({"status": "success"})

def _update_voter_stats(voter_id):
    """Update voter's total votes and agreement rate."""
    # Get voter's total votes
    res = supabase.table("match_history").select("id").eq("voter_id", voter_id).execute()
    total_votes = len(res.data)

    # Get voter's agreement rate (how often they voted with the majority)
    # This is a simplified calculation — a full implementation would compare
    # each vote against the consensus of all voters on the same pair
    res_all = supabase.table("match_history").select("winner_id, loser_id, voter_id").execute()
    all_votes = res_all.data

    # Count how many of this voter's votes agree with the majority
    agreements = 0
    total_comparable = 0

    # Group votes by pair
    pair_votes = {}
    for v in all_votes:
        pair = tuple(sorted([v["winner_id"], v["loser_id"]]))
        if pair not in pair_votes:
            pair_votes[pair] = []
        pair_votes[pair].append(v)

    # For each pair this voter voted on, check if they agreed with majority
    voter_pairs = [tuple(sorted([v["winner_id"], v["loser_id"]])) for v in all_votes if v["voter_id"] == voter_id]
    for pair in set(voter_pairs):
        votes_on_pair = pair_votes.get(pair, [])
        if len(votes_on_pair) < 2:
            continue
        # Count votes for each site
        a, b = pair
        a_votes = sum(1 for v in votes_on_pair if v["winner_id"] == a)
        b_votes = sum(1 for v in votes_on_pair if v["winner_id"] == b)
        majority = a if a_votes > b_votes else b
        # Did this voter agree?
        voter_vote = [v for v in votes_on_pair if v["voter_id"] == voter_id][0]
        total_comparable += 1
        if voter_vote["winner_id"] == majority:
            agreements += 1

    agreement_rate = agreements / total_comparable if total_comparable > 0 else 0.0

    # Upsert voter stats
    supabase.table("voters").upsert({
        "voter_id": voter_id,
        "total_votes": total_votes,
        "agreement_rate": round(agreement_rate, 3)
    }).execute()

@app.route("/api/voter_stats", methods=["GET"])
def voter_stats():
    if not supabase:
        return jsonify({"error": "Supabase not configured"}), 500

    voter_id = request.args.get("voter_id")
    if voter_id:
        # Single voter stats
        res = supabase.table("voters").select("*").eq("voter_id", voter_id).execute()
        if not res.data:
            return jsonify({"error": "Voter not found"}), 404
        return jsonify(res.data[0])
    else:
        # All voters (for leaderboard)
        res = supabase.table("voters").select("*").order("agreement_rate", desc=True).execute()
        return jsonify({"voters": res.data})

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
    app.run(port=5001)
