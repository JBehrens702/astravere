import json
import os
import random
import math
import string
import time
from pathlib import Path

STATE_DIR = Path("game_states")
STATE_DIR.mkdir(exist_ok=True)


def state_path(room_code: str) -> Path:
    return STATE_DIR / f"{room_code}.json"


def generate_room_code() -> str:
    return "".join(random.choices(string.ascii_uppercase, k=5))


def parse_quotebook(text: str) -> list[dict]:
    quotes = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if " - " in line:
            parts = line.rsplit(" - ", 1)
            quote_text = parts[0].strip().strip('"').strip("\u201c\u201d")
            author = parts[1].strip()
        else:
            quote_text = line.strip('"').strip("\u201c\u201d")
            author = "Unknown"
        if quote_text:
            quotes.append({"text": quote_text, "author": author})
    return quotes


def next_power_of_two(n: int) -> int:
    return 2 ** math.ceil(math.log2(n)) if n > 1 else 2


def build_bracket(quotes: list[dict]) -> list[list[dict | None]]:
    """
    Build first-round matchups. Try to keep same-author quotes in the same
    half of the bracket so they can only meet in later rounds.
    Returns list of pairs: [[q1, q2], [q3, q4], ...]
    At most one BYE is added if there's an odd number of quotes.
    """
    # Only add one BYE if odd number of quotes
    num_quotes = len(quotes)
    padded = quotes[:]
    random.shuffle(padded)
    if num_quotes % 2 == 1:
        padded.append(None)  # Only one BYE
    
    size = len(padded)

    # Group by author, spread authors across bracket halves
    by_author: dict[str, list] = {}
    for q in padded:
        if q is None:
            continue
        by_author.setdefault(q["author"], []).append(q)

    # Sort authors by count descending so big authors get spread first
    ordered = []
    authors_sorted = sorted(by_author.keys(), key=lambda a: -len(by_author[a]))
    for author in authors_sorted:
        ordered.extend(by_author[author])

    # Fill slots using a "snake" pattern to spread same-author quotes
    slots = [None] * size
    indices = list(range(size))
    # Interleave: 0, size-1, size//2, size//2-1, ...
    spread = []
    lo, hi = 0, size - 1
    toggle = True
    while lo <= hi:
        if toggle:
            spread.append(lo)
            lo += 1
        else:
            spread.append(hi)
            hi -= 1
        toggle = not toggle

    for i, q in enumerate(ordered):
        slots[spread[i]] = q

    pairs = [[slots[i], slots[i + 1]] for i in range(0, size, 2)]
    return pairs


def create_game(quotes: list[dict], host_name: str) -> str:
    room_code = generate_room_code()
    pairs = build_bracket(quotes)

    # Convert to serializable matchups
    matchups = []
    for pair in pairs:
        matchups.append({
            "a": pair[0],
            "b": pair[1],
            "votes": {"a": [], "b": []},
            "winner": None,
        })

    state = {
        "room_code": room_code,
        "host": host_name,
        "status": "lobby",      # lobby | voting | results | done
        "round": 1,
        "total_rounds": int(math.log2(len(pairs) * 2)),
        "matchups": matchups,   # current round matchups
        "bracket_history": [],  # list of past round matchup lists
        "participants": {},     # name -> last_seen timestamp
        "created_at": time.time(),
    }

    save_state(room_code, state)
    return room_code


def load_state(room_code: str) -> dict | None:
    p = state_path(room_code)
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)


def save_state(room_code: str, state: dict):
    with open(state_path(room_code), "w") as f:
        json.dump(state, f, indent=2)


def join_game(room_code: str, player_name: str) -> bool:
    state = load_state(room_code)
    if state is None:
        return False
    state["participants"][player_name] = time.time()
    save_state(room_code, state)
    return True


def cast_vote(room_code: str, matchup_index: int, player_name: str, choice: str):
    """choice is 'a' or 'b'"""
    state = load_state(room_code)
    if state is None:
        return
    m = state["matchups"][matchup_index]
    # Remove any prior vote by this player
    for side in ("a", "b"):
        if player_name in m["votes"][side]:
            m["votes"][side].remove(player_name)
    m["votes"][choice].append(player_name)
    save_state(room_code, state)


def get_vote_counts(matchup: dict) -> tuple[int, int]:
    return len(matchup["votes"]["a"]), len(matchup["votes"]["b"])


def all_voted(state: dict) -> bool:
    """True if every active participant has voted in every matchup (skipping byes)."""
    participants = set(state["participants"].keys())
    for m in state["matchups"]:
        if m["a"] is None or m["b"] is None:
            continue  # bye — no vote needed
        voted = set(m["votes"]["a"]) | set(m["votes"]["b"])
        if not participants.issubset(voted):
            return False
    return True


def advance_round(room_code: str):
    """Resolve current round and build next round matchups."""
    state = load_state(room_code)
    winners = []
    for m in state["matchups"]:
        if m["a"] is None:
            winners.append(m["b"])
        elif m["b"] is None:
            winners.append(m["a"])
        else:
            va, vb = get_vote_counts(m)
            if va >= vb:
                m["winner"] = "a"
                winners.append(m["a"])
            else:
                m["winner"] = "b"
                winners.append(m["b"])

    state["bracket_history"].append(state["matchups"])

    if len(winners) == 1:
        state["status"] = "done"
        state["champion"] = winners[0]
        state["matchups"] = []
    else:
        state["round"] += 1
        state["matchups"] = [
            {"a": winners[i], "b": winners[i + 1], "votes": {"a": [], "b": []}, "winner": None}
            for i in range(0, len(winners), 2)
        ]
        state["status"] = "results"

    save_state(room_code, state)


def start_voting(room_code: str):
    state = load_state(room_code)
    state["status"] = "voting"
    save_state(room_code, state)


def get_player_votes(state: dict, player_name: str) -> dict[int, str]:
    """Returns {matchup_index: 'a'|'b'} for all votes cast by player."""
    votes = {}
    for i, m in enumerate(state["matchups"]):
        if player_name in m["votes"]["a"]:
            votes[i] = "a"
        elif player_name in m["votes"]["b"]:
            votes[i] = "b"
    return votes