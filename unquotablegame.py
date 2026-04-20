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
    Build first-round matchups.
    Strategy:
      1. Group quotes by author and shuffle within each group.
      2. Pair same-author quotes together (so they can only meet later).
      3. Collect the one leftover per author that has an odd count.
      4. Shuffle those leftover singles and pair them with each other.
      5. If there's still one unpaired single, give it the sole BYE.
    Result: at most ONE BYE, same-author quotes never meet in round 1.
    """
    # Group and shuffle within each author
    by_author: dict[str, list] = {}
    for q in quotes:
        by_author.setdefault(q["author"], []).append(q)
    for lst in by_author.values():
        random.shuffle(lst)

    same_author_pairs: list[list] = []
    singles: list[dict] = []

    for author_qs in by_author.values():
        for i in range(0, len(author_qs) - 1, 2):
            same_author_pairs.append([author_qs[i], author_qs[i + 1]])
        if len(author_qs) % 2 == 1:
            singles.append(author_qs[-1])

    # Pair up the leftover singles with each other (cross-author)
    random.shuffle(singles)
    cross_pairs: list[list] = []
    for i in range(0, len(singles) - 1, 2):
        cross_pairs.append([singles[i], singles[i + 1]])

    # At most one BYE for the final unpaired single
    bye_pair: list[list] = []
    if len(singles) % 2 == 1:
        bye_pair.append([singles[-1], None])

    all_pairs = same_author_pairs + cross_pairs + bye_pair
    random.shuffle(all_pairs)
    return all_pairs


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
        "total_rounds": math.ceil(math.log2(len(quotes))) if len(quotes) > 1 else 1,
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
        # If an odd number of winners, the top seed gets a BYE this round
        if len(winners) % 2 == 1:
            winners.append(None)
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