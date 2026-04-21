import json
import os
import random
import math
import re
import string
import time
from pathlib import Path
from filelock import FileLock

STATE_DIR = Path("game_states")
STATE_DIR.mkdir(exist_ok=True)


def state_path(room_code: str) -> Path:
    return STATE_DIR / f"{room_code}.json"


def lock_path(room_code: str) -> Path:
    """Get the lock file path for a room code."""
    return STATE_DIR / f"{room_code}.lock"


def generate_room_code() -> str:
    return "".join(random.choices(string.ascii_uppercase, k=5))


# ── Quote parsing helpers ─────────────────────────────────────────────────────

# Detects one Name: "Quote" segment within a line.
# Name must start with a letter; must not contain : or " (prevents false matches
# on context strings like "(After checking the code)").
_SPEAKER_SEG_RE = re.compile(r'([A-Za-z][^:"]*?):\s*"([^"]*)"')

# Matches a full single-speaker line, quoted OR unquoted text.
# Requires name to start with a letter so context lines starting with ( are skipped.
_COLON_RE = re.compile(r'^([A-Za-z][^:"\n]*):\s*(.+)$')


def _strip_outer_quotes(s: str) -> str:
    """Strip surrounding quotes only when the string is fully wrapped in them."""
    if len(s) >= 2 and (
        (s[0] == '"'      and s[-1] == '"') or
        (s[0] == '\u201c' and s[-1] == '\u201d')
    ):
        return s[1:-1]
    return s


def _clean_text(s: str) -> str:
    """Remove a lone leading quote left after partial stripping."""
    if s and s[0] in '"\u201c':
        s = s[1:]
        if s and s[-1] in '"\u201d':
            s = s[:-1]
    return s


def _parse_line(line: str) -> dict | None:
    """Parse one logical line into {text, author}. Returns None if empty."""

    # ── (Context) "Quote" - Author  OR  "Quote" - Author ──────────────────
    if " - " in line:
        parts = line.rsplit(" - ", 1)
        quote_text = _clean_text(_strip_outer_quotes(parts[0].strip()))
        author = parts[1].strip() or None
        if quote_text:
            return {"text": quote_text, "author": author}

    # ── Name: "Quote"  OR  Name: Quote (without quotes) ───────────────────
    m = _COLON_RE.match(line)
    if m:
        author = m.group(1).strip() or None
        quote_text = _clean_text(_strip_outer_quotes(m.group(2).strip()))
        if quote_text:
            return {"text": quote_text, "author": author}

    # ── Plain text, no author ──────────────────────────────────────────────
    quote_text = _clean_text(_strip_outer_quotes(line))
    if quote_text:
        return {"text": quote_text, "author": None}

    return None


def parse_quotebook(text: str) -> list[dict]:
    """
    Supported formats (one per line, blank lines ignored):

      "Quote" - Author
      (Context) "Quote" - Author     context kept in text, author extracted
      Author: "Quote"                colon-author with quoted text
      Author: Quote                  colon-author without quotes
      A: "X"  B: "Y"  C: "Z"        multi-speaker on one line (tab- or
                                     space-separated); full line kept as text,
                                     authors joined as "A, B, C"
      plain text                     displayed as-is, no author

    Tabs between entries on one line are treated as multi-speaker separators
    only when each segment matches Name: "Quote". Otherwise tabs separate
    independent individual entries.
    """
    quotes = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # ── Multi-speaker on one line: 2+ Name: "Quote" segments ──────────
        segs = _SPEAKER_SEG_RE.findall(line)
        if len(segs) >= 2:
            authors = ", ".join(name.strip() for name, _ in segs)
            quotes.append({"text": line, "author": authors})
            continue

        # ── Tabs separate independent entries (non-multi-speaker) ──────────
        parts = [p.strip() for p in line.split("\t") if p.strip()]
        for part in parts:
            q = _parse_line(part)
            if q:
                quotes.append(q)

    return quotes


def next_power_of_two(n: int) -> int:
    return 2 ** math.ceil(math.log2(n)) if n > 1 else 2


def build_bracket(quotes: list[dict]) -> list[list[dict | None]]:
    """
    Build first-round matchups.
    Strategy:
      1. Group quotes by author and shuffle within each group.
      2. Pair same-author quotes together (so they can only meet in later rounds).
      3. Collect the leftover single per author that has an odd count.
      4. Shuffle those singles and pair them cross-author.
      5. If one single remains unpaired, it gets the sole BYE.
    Result: at most ONE BYE; same-author quotes never face each other in round 1.
    """
    by_author: dict[str, list] = {}
    for i, q in enumerate(quotes):
        # Authorless quotes each get a unique key so they're never grouped together
        key = q["author"] if q.get("author") else f"__anon_{i}__"
        by_author.setdefault(key, []).append(q)
    for lst in by_author.values():
        random.shuffle(lst)

    same_author_pairs: list[list] = []
    singles: list[dict] = []

    for author_qs in by_author.values():
        for i in range(0, len(author_qs) - 1, 2):
            same_author_pairs.append([author_qs[i], author_qs[i + 1]])
        if len(author_qs) % 2 == 1:
            singles.append(author_qs[-1])

    random.shuffle(singles)
    cross_pairs: list[list] = []
    for i in range(0, len(singles) - 1, 2):
        cross_pairs.append([singles[i], singles[i + 1]])

    bye_pair: list[list] = []
    if len(singles) % 2 == 1:
        bye_pair.append([singles[-1], None])

    all_pairs = same_author_pairs + cross_pairs + bye_pair
    random.shuffle(all_pairs)
    return all_pairs


def create_game(quotes: list[dict]) -> str:
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
    
    lock_file = FileLock(str(lock_path(room_code)), timeout=10)
    try:
        with lock_file:
            try:
                with open(p) as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                print(f"ERROR: Corrupted JSON in {room_code}: {e}")
                # Try to load from backup if available
                backup_p = Path(str(p) + ".backup")
                if backup_p.exists():
                    try:
                        with open(backup_p) as f:
                            state = json.load(f)
                        print(f"Recovered from backup for {room_code}")
                        return state
                    except json.JSONDecodeError:
                        print(f"ERROR: Backup also corrupted for {room_code}")
                        return None
                return None
            except Exception as e:
                print(f"ERROR: Failed to load state for {room_code}: {e}")
                return None
    except Exception as e:
        print(f"ERROR: Failed to acquire lock for {room_code}: {e}")
        return None


def save_state(room_code: str, state: dict):
    p = state_path(room_code)
    lock_file = FileLock(str(lock_path(room_code)), timeout=10)
    
    try:
        with lock_file:
            # Atomic write: write to temp file first, then rename
            # This prevents corruption if write is interrupted
            temp_p = Path(str(p) + ".tmp")
            try:
                with open(temp_p, "w") as f:
                    json.dump(state, f, indent=2)
                # Create backup before replacing main file
                if p.exists():
                    backup_p = Path(str(p) + ".backup")
                    p.rename(backup_p)
                # Move temp file to main location
                temp_p.rename(p)
            except Exception as e:
                print(f"ERROR: Failed to save state for {room_code}: {e}")
                # Clean up temp file if something went wrong
                if temp_p.exists():
                    temp_p.unlink()
    except Exception as e:
        print(f"ERROR: Failed to acquire lock for {room_code}: {e}")


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
    if state is None:
        print(f"ERROR: Cannot advance round - state corrupted for {room_code}")
        return
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
        state["matchups"] = []
        for i in range(0, len(winners), 2):
            if i + 1 < len(winners):
                # Normal pairing
                state["matchups"].append({
                    "a": winners[i], 
                    "b": winners[i + 1], 
                    "votes": {"a": [], "b": []}, 
                    "winner": None
                })
            else:
                # Odd winner gets a BYE to next round
                state["matchups"].append({
                    "a": winners[i], 
                    "b": None, 
                    "votes": {"a": [], "b": []}, 
                    "winner": None
                })
        state["status"] = "results"

    save_state(room_code, state)


def start_voting(room_code: str):
    state = load_state(room_code)
    if state is None:
        print(f"ERROR: Cannot start voting - state corrupted for {room_code}")
        return
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
