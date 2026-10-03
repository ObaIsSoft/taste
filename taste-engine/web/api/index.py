"""Voting API for the TASTE engine (a Flask function on Vercel).

Every voting rule lives in Postgres (supabase/migrations/0001_v2_voting.sql).
This layer only checks the invite code, calls the voting functions, signs
short-lived media URLs and turns database errors into HTTP status codes.

Environment: SUPABASE_URL, SUPABASE_SERVICE_KEY, TASTE_STORAGE_BUCKET, and
optionally TASTE_SIGNED_URL_SECONDS.
"""

from __future__ import annotations

import logging
import os
from functools import cache
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_from_directory
from postgrest.exceptions import APIError

from supabase import Client, create_client

PUBLIC_DIR = Path(__file__).resolve().parent.parent / "public"
SIGNED_URL_SECONDS = int(os.environ.get("TASTE_SIGNED_URL_SECONDS", "3600"))
ROUNDS = ("visual", "motion")
EVENTS = (
    "play_left",
    "play_right",
    "open_live_left",
    "open_live_right",
    "view_left",
    "view_right",
    "scroll_left",
    "scroll_right",
)

# SQLSTATE raised by the voting functions -> HTTP status
STATUS_FOR = {
    "28000": 401,
    "22023": 400,
    "22P02": 400,
    "23505": 409,
    "P0002": 404,
    "P0429": 429,
}

app = Flask(__name__, static_folder=str(PUBLIC_DIR), static_url_path="")
log = logging.getLogger(__name__)


@cache
def db() -> Client:
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


class BadRequest(Exception):
    pass


@app.errorhandler(APIError)
def _database_error(error: APIError):
    status = STATUS_FOR.get(error.code or "", 500)
    if status == 500:
        log.error("database error %s: %s", error.code, error.message)
        return jsonify(error="Something went wrong on our side. Please try again."), 500
    return jsonify(error=error.message), status


@app.errorhandler(BadRequest)
def _bad_request(error: BadRequest):
    return jsonify(error=str(error)), 400


def _code() -> str:
    code = request.headers.get("X-Invite-Code", "").strip()
    if not code:
        raise APIError({"code": "28000", "message": "Sign in with your invite code."})
    return code


def _rpc(name: str, params: dict[str, Any]) -> Any:
    return db().rpc(name, params).execute().data


def _signed(paths: list[str]) -> dict[str, str]:
    if not paths:
        return {}
    bucket = os.environ["TASTE_STORAGE_BUCKET"]
    signed = db().storage.from_(bucket).create_signed_urls(paths, SIGNED_URL_SECONDS)
    return {item["path"]: item["signedURL"] for item in signed if not item.get("error")}


def _side(capture: dict[str, Any], urls: dict[str, str]) -> dict[str, Any]:
    return {
        "stills": [urls[p] for p in capture["stills"] if p in urls],
        "reel": urls.get(capture["reel_path"]) if capture["reel_path"] else None,
        "live_url": capture["final_url"] or capture["sites"]["url"],
    }


@app.get("/")
def index():
    return send_from_directory(PUBLIC_DIR, "index.html")


@app.get("/api/config")
def config():
    """The dimensions with their definitions, the limits a vote must meet, and per round the
    target, calibration pairs and repeats. Public: the voter guide shows it before sign-in."""
    dimensions = (
        db()
        .table("dimensions")
        .select("id,label,description,round,position")
        .order("position")
        .execute()
        .data
    )
    facts = _rpc("voting_facts", {})
    return jsonify(
        dimensions={r: [d for d in dimensions if d["round"] == r] for r in ROUNDS}, **facts
    )


@app.post("/api/session")
def session():
    code = _code()
    progress = _rpc("voter_progress", {"p_code": code})
    [voter] = db().table("voters").select("name").eq("invite_code", code).execute().data
    return jsonify(name=voter["name"], progress=progress)


@app.get("/api/progress")
def progress():
    return jsonify(progress=_rpc("voter_progress", {"p_code": _code()}))


@app.get("/api/pair")
def pair():
    round_kind = request.args.get("round", "visual")
    if round_kind not in ROUNDS:
        raise BadRequest("round must be visual or motion")
    served = _rpc("next_pair", {"p_code": _code(), "p_round": round_kind})
    ids = [served["left_capture"], served["right_capture"]]
    rows = (
        db()
        .table("captures")
        .select("id,stills,reel_path,final_url,sites(url)")
        .in_("id", ids)
        .execute()
        .data
    )
    captures = {row["id"]: row for row in rows}
    paths = [p for row in rows for p in row["stills"]]
    paths += [row["reel_path"] for row in rows if row["reel_path"] and round_kind == "motion"]
    urls = _signed(paths)
    return jsonify(
        token=served["token"],
        round=round_kind,
        reason_requested=served["reason_requested"],
        left=_side(captures[ids[0]], urls),
        right=_side(captures[ids[1]], urls),
    )


@app.get("/api/terms")
def terms():
    """The voter's own past words for a round, most used first, to suggest as they type."""
    round_kind = request.args.get("round", "visual")
    if round_kind not in ROUNDS:
        raise BadRequest("round must be visual or motion")
    rows = _rpc("voter_terms", {"p_code": _code(), "p_round": round_kind})
    return jsonify(terms=[row["term"] for row in rows or []])


@app.post("/api/vote")
def vote():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise BadRequest("send a JSON object")
    dimensions = body.get("dimensions") or []
    own_terms = body.get("terms") or []
    reason = body.get("reason")
    client = body.get("client") or {}
    if not isinstance(client, dict):  # its size limit is in voting_config, checked by cast_vote
        raise BadRequest("client must be an object")
    if not isinstance(dimensions, list) or not all(isinstance(d, str) for d in dimensions):
        raise BadRequest("dimensions must be a list of names")
    if not isinstance(own_terms, list) or not all(isinstance(t, str) for t in own_terms):
        raise BadRequest("terms must be a list of words")
    if reason is not None and not isinstance(reason, str):
        raise BadRequest("reason must be text")
    vote_id = _rpc(
        "cast_vote",
        {
            "p_code": _code(),
            "p_token": body.get("token"),
            "p_outcome": body.get("outcome"),
            "p_dimensions": dimensions,
            "p_reason": reason,
            "p_terms": own_terms,
            "p_client": client,
        },
    )
    return jsonify(vote_id=vote_id)


@app.post("/api/event")
def event():
    body = request.get_json(silent=True) or {}
    if body.get("kind") not in EVENTS:
        raise BadRequest("unknown event")
    _rpc("log_event", {"p_code": _code(), "p_token": body.get("token"), "p_kind": body["kind"]})
    return jsonify(ok=True)


if __name__ == "__main__":  # local development: serves the API and the static pages
    app.run(port=int(os.environ.get("PORT", "5001")))
