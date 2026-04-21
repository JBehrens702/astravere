import streamlit as st
import time
import os
from unquotablegame import (
    parse_quotebook,
    create_game,
    load_state,
    join_game,
    cast_vote,
    advance_round,
    start_voting,
    get_vote_counts,
    get_player_votes,
    all_voted,
)

st.set_page_config(
    page_title="[UN]Quotable - The Game",
    page_icon="❝",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Constants ─────────────────────────────────────────────────────────────────
GITHUB_QR_URL = "https://raw.githubusercontent.com/JBehrens702/astravere/main/qrcode.png"

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
    background: #0f0f13;
    color: #e8e6e1;
}
.stApp { background: #0f0f13; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 2rem; padding-bottom: 2rem; max-width: 900px; }
h1, h2, h3 { font-family: 'DM Serif Display', serif; font-weight: 400; }
hr { border-color: #2a2a35; }

.room-code {
    font-family: 'DM Sans', monospace;
    font-size: 3.5rem;
    font-weight: 600;
    letter-spacing: 0.3em;
    color: #f0c060;
    text-align: center;
    padding: 1.5rem;
    background: #18181f;
    border: 1px solid #2a2a35;
    border-radius: 12px;
    margin: 1rem 0;
}

.quote-card {
    background: #18181f;
    border: 1px solid #2a2a35;
    border-radius: 12px;
    padding: 1.5rem 1.8rem;
    margin: 0.5rem 0;
    min-height: 110px;
}
.quote-card.selected { border-color: #4f8ef7; background: #141826; }
.quote-text {
    font-family: 'DM Serif Display', serif;
    font-size: 1.15rem;
    line-height: 1.65;
    color: #e8e6e1;
    font-style: italic;
}
.quote-author {
    font-size: 0.78rem;
    color: #888;
    margin-top: 0.6rem;
    font-weight: 500;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}

.vote-bar-wrap {
    background: #0f0f13;
    border-radius: 6px;
    height: 6px;
    overflow: hidden;
}
.vote-bar-fill {
    height: 6px;
    border-radius: 6px;
    background: #4f8ef7;
}

.vs-label {
    text-align: center;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.2em;
    color: #555;
    text-transform: uppercase;
}

.participant-chip {
    display: inline-block;
    background: #18181f;
    border: 1px solid #2a2a35;
    border-radius: 999px;
    padding: 0.2rem 0.75rem;
    font-size: 0.8rem;
    color: #aaa;
    margin: 0.15rem;
}

.champion-card {
    background: linear-gradient(135deg, #1a1a25 0%, #221e10 100%);
    border: 1px solid #f0c060;
    border-radius: 16px;
    padding: 2.5rem;
    text-align: center;
    margin: 1rem 0;
}
.champion-label {
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.2em;
    color: #f0c060;
    text-transform: uppercase;
    margin-bottom: 0.5rem;
}
.champion-quote {
    font-family: 'DM Serif Display', serif;
    font-size: 1.8rem;
    font-style: italic;
    line-height: 1.5;
    color: #e8e6e1;
}
.champion-author {
    margin-top: 1rem;
    font-size: 0.9rem;
    color: #f0c060;
    font-weight: 500;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}

.stButton > button {
    background: #1e2030;
    color: #c8c6c1;
    border: 1px solid #2a2a35;
    border-radius: 8px;
    font-family: 'DM Sans', sans-serif;
    font-weight: 500;
    transition: all 0.15s;
}
.stButton > button:hover {
    background: #4f8ef7 !important;
    color: white !important;
    border-color: #4f8ef7 !important;
}
.stTextInput > div > div > input {
    background: #18181f;
    border: 1px solid #2a2a35;
    border-radius: 8px;
    color: #e8e6e1;
    font-family: 'DM Sans', sans-serif;
}
</style>
""", unsafe_allow_html=True)


# ── Session state defaults ────────────────────────────────────────────────────
for k, v in [("mode", None), ("room_code", None), ("player_name", None)]:
    if k not in st.session_state:
        st.session_state[k] = v


# ── Helpers ───────────────────────────────────────────────────────────────────
def display_text(text: str, max_len: int = 70) -> str:
    """Flatten newlines to ' / ' and truncate for use in inline contexts."""
    flat = text.replace("\n", " / ")
    return flat[:max_len] + ("…" if len(flat) > max_len else "")


def render_quote_card(quote, selected=False, show_author=False):
    css = "selected" if selected else ""
    author_html = (
        f'<div class="quote-author">— {quote["author"]}</div>'
        if show_author and quote.get("author")
        else ""
    )
    raw_text = quote["text"]
    if "\n" in raw_text:
        # Multi-line dialogue: preserve line breaks, no outer curly quotes
        inner = raw_text.replace("\n", "<br>")
        quote_html = f'<div class="quote-text">{inner}</div>'
    else:
        quote_html = f'<div class="quote-text">&#x201C;{raw_text}&#x201D;</div>'
    st.markdown(f"""
    <div class="quote-card {css}">
        {quote_html}
        {author_html}
    </div>
    """, unsafe_allow_html=True)


def render_vote_bar(va, vb):
    total = va + vb
    pct = int(va / total * 100) if total else 50
    st.markdown(f"""
    <div style="display:flex;gap:0.5rem;align-items:center;margin-top:0.5rem;">
        <span style="font-size:0.8rem;color:#4f8ef7;font-weight:600;min-width:1.5rem;">{va}</span>
        <div class="vote-bar-wrap" style="flex:1">
            <div class="vote-bar-fill" style="width:{pct}%"></div>
        </div>
        <span style="font-size:0.8rem;color:#888;font-weight:600;min-width:1.5rem;text-align:right;">{vb}</span>
    </div>
    """, unsafe_allow_html=True)

# ── Bracket Visualization ─────────────────────────────────────────────────────
def build_bracket_layers(state: dict) -> list[list]:
    """
    Organize bracket into layers: past rounds (from history) + current round.
    Returns: [round1_matchups, round2_matchups, ..., current_round_matchups]
    """
    layers = []
    for past_round in state["bracket_history"]:
        layers.append(past_round)
    layers.append(state["matchups"])
    return layers


def render_bracket_visualization(state: dict, total_participants: int):
    """
    Render interactive bracket using Plotly.
    Shows all rounds horizontally with vote counts and progression.
    """
    import plotly.graph_objects as go
    
    layers = build_bracket_layers(state)
    num_rounds = len(layers)
    
    # Layout parameters
    x_spacing = 1.0
    y_spacing = 2.0
    x_pos = [i * x_spacing for i in range(num_rounds)]
    
    # Collect all nodes and edges
    node_x, node_y = [], []
    node_text, node_hover = [], []
    node_color = []
    edge_x, edge_y = [], []
    
    node_id_map = {}  # (round, matchup_idx, side) -> node_id
    node_counter = 0
    
    # Build nodes for each round
    for round_idx, matchups in enumerate(layers):
        # Calculate vertical positions for this round
        num_matchups = sum(1 for m in matchups if m["a"] and m["b"])
        y_positions = [-(i * y_spacing - (num_matchups - 1) * y_spacing / 2) for i in range(num_matchups)]
        
        matchup_counter = 0
        for m_idx, m in enumerate(matchups):
            if m["a"] is None or m["b"] is None:
                continue  # Skip byes
            
            y = y_positions[matchup_counter]
            matchup_counter += 1
            
            # Get vote counts
            va, vb = get_vote_counts(m)
            total_votes = va + vb
            
            # Determine winner
            winner_side = m.get("winner")
            is_completed = round_idx < len(layers) - 1  # Past rounds are completed
            
            # Winner node (shows the advancing quote)
            if is_completed:
                winner_quote = m["a"] if winner_side == "a" else m["b"]
                winner_votes = va if winner_side == "a" else vb
                loser_votes = vb if winner_side == "a" else va
            else:
                # Current round: show leading quote (if any votes) or pick a, b arbitrarily
                if va > vb:
                    winner_quote = m["a"]
                    winner_votes = va
                    loser_votes = vb
                elif vb > va:
                    winner_quote = m["b"]
                    winner_votes = vb
                    loser_votes = va
                else:
                    # Tied: show A
                    winner_quote = m["a"]
                    winner_votes = va
                    loser_votes = vb
            
            # Node ID
            node_id = node_counter
            node_id_map[(round_idx, m_idx)] = node_id
            node_counter += 1
            
            # Node position
            node_x.append(x_pos[round_idx])
            node_y.append(y)
            
            # Node appearance
            status_indicator = "✓" if is_completed else ""
            quote_snippet = winner_quote["text"][:45]
            if len(winner_quote["text"]) > 45:
                quote_snippet += "…"
            
            node_text.append(f"{status_indicator}")
            hover_text = (
                f"<b>{winner_quote.get('author') or 'Unknown'}</b><br>"
                f"<i>\"{winner_quote['text'][:80]}{'…' if len(winner_quote['text']) > 80 else ''}<i><br>"
                f"Votes: <b>{winner_votes}</b> vs {loser_votes}"
            )
            node_hover.append(hover_text)
            
            # Color: blue for winners in completed rounds, gray for current
            if is_completed:
                node_color.append("#4f8ef7")  # Blue
            else:
                node_color.append("#888")  # Gray for voting
    
    # Build edges (progression lines) between consecutive rounds
    for round_idx in range(len(layers) - 1):
        current_nodes = [k for k in node_id_map.keys() if k[0] == round_idx]
        next_nodes = [k for k in node_id_map.keys() if k[0] == round_idx + 1]
        
        # Each pair of nodes in current round feeds into one node in next round
        for next_node_key in next_nodes:
            # Find which current round matchups feed into this next round matchup
            # For a proper bracket: matchups [0,1] -> 0, [2,3] -> 1, etc.
            next_m_idx = next_node_key[1]
            source_m_indices = [next_m_idx * 2, next_m_idx * 2 + 1]
            
            for src_idx in source_m_indices:
                src_key = (round_idx, src_idx)
                if src_key in node_id_map:
                    src_id = node_id_map[src_key]
                    dst_id = node_id_map[next_node_key]
                    
                    # Draw line from source to destination
                    x0, y0 = node_x[src_id], node_y[src_id]
                    x1, y1 = node_x[dst_id], node_y[dst_id]
                    
                    edge_x.extend([x0, x1, None])
                    edge_y.extend([y0, y1, None])
    
    # Create Plotly figure
    fig = go.Figure()
    
    # Add edges (progression lines)
    if edge_x:
        fig.add_trace(go.Scatter(
            x=edge_x, y=edge_y,
            mode='lines',
            line=dict(width=1.5, color='#2a2a35'),
            hoverinfo='none',
            showlegend=False,
        ))
    
    # Add nodes (matchup results)
    fig.add_trace(go.Scatter(
        x=node_x, y=node_y,
        mode='markers+text',
        marker=dict(
            size=20,
            color=node_color,
            line=dict(width=2, color='#18181f'),
        ),
        text=node_text,
        textposition='middle center',
        textfont=dict(size=10, color='white', family='DM Sans'),
        hovertext=node_hover,
        hoverinfo='text',
        showlegend=False,
    ))
    
    # Update layout to match Streamlit's dark theme
    fig.update_layout(
        title=dict(
            text=f"Bracket Overview",
            x=0.5,
            xanchor='center',
            font=dict(size=16, family='DM Serif Display', color='#e8e6e1')
        ),
        xaxis=dict(
            tickvals=x_pos,
            ticktext=[f"Round {i+1}" for i in range(num_rounds)],
            tickfont=dict(size=11, color='#888', family='DM Sans'),
            showgrid=False,
            zeroline=False,
            showline=False,
        ),
        yaxis=dict(
            showgrid=False,
            zeroline=False,
            showline=False,
            showticklabels=False,
        ),
        plot_bgcolor='#0f0f13',
        paper_bgcolor='#0f0f13',
        hovermode='closest',
        margin=dict(l=40, r=40, t=60, b=40),
        height=600,
        font=dict(family='DM Sans', color='#e8e6e1'),
    )
    
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

# ── Landing ───────────────────────────────────────────────────────────────────
def page_landing():
    st.markdown("<h1 style='text-align:center;font-size:2.8rem;margin-bottom:0.25rem;'>[UN]Quotable - The Game</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center;color:#555;font-size:1rem;margin-bottom:3rem;'>The ultimate quotebook showdown</p>", unsafe_allow_html=True)
    col1, _, col2 = st.columns([1, 0.15, 1])
    with col1:
        st.markdown("#### Host a Game")
        st.markdown("<p style='color:#666;font-size:0.88rem;'>Import your quotebook and run the bracket.</p>", unsafe_allow_html=True)
        if st.button("🎮  Host", use_container_width=True):
            st.session_state.mode = "host_setup"
            st.rerun()
    with col2:
        st.markdown("#### Join a Game")
        st.markdown("<p style='color:#666;font-size:0.88rem;'>Enter the room code from your host.</p>", unsafe_allow_html=True)
        if st.button("🙋  Join", use_container_width=True):
            st.session_state.mode = "join_setup"
            st.rerun()


# ── Host Setup ────────────────────────────────────────────────────────────────
def page_host_setup():
    st.markdown("## Host Setup")
    st.markdown("---")
    host_name = st.text_input("Your name", placeholder="Host")
    uploaded = st.file_uploader("Upload quotebook (.txt)", type=["txt"])

    if uploaded and host_name:
        text = uploaded.read().decode("utf-8", errors="replace")
        quotes = parse_quotebook(text)
        st.markdown(f"**{len(quotes)} quotes** parsed.")

        if len(quotes) < 2:
            st.error("Need at least 2 quotes.")
            return

        with st.expander("Preview"):
            for q in quotes[:10]:
                author_str = f" — {q['author']}" if q.get("author") else ""
                st.markdown(f'- *"{display_text(q["text"], 80)}"*{author_str}')
            if len(quotes) > 10:
                st.markdown(f"*…and {len(quotes)-10} more*")

        if st.button("🚀  Create Game", use_container_width=True):
            room_code = create_game(quotes, host_name)
            st.session_state.room_code = room_code
            st.session_state.player_name = host_name
            st.session_state.mode = "host"
            st.rerun()

    if st.button("← Back"):
        st.session_state.mode = None
        st.rerun()


# ── Join Setup ────────────────────────────────────────────────────────────────
def page_join_setup():
    st.markdown("## Join a Game")
    st.markdown("---")
    code = st.text_input("Room code", max_chars=5, placeholder="ABCDE").strip().upper()
    name = st.text_input("Your name", placeholder="Player")

    if st.button("Join →", use_container_width=True):
        if not code or not name:
            st.error("Please enter both fields.")
        else:
            ok = join_game(code, name)
            if not ok:
                st.error("Room not found.")
            else:
                st.session_state.room_code = code
                st.session_state.player_name = name
                st.session_state.mode = "participant"
                st.rerun()

    if st.button("← Back"):
        st.session_state.mode = None
        st.rerun()


# ── HOST VIEW ─────────────────────────────────────────────────────────────────
def page_host():
    code = st.session_state.room_code
    state = load_state(code)
    if not state:
        st.error("Game state not found.")
        return
    
    st.markdown(f"## Round {state['round']} of {state['total_rounds']}")

    col_left, col_center, col_right = st.columns([3, 1, 1])
    with col_left:
        st.markdown(f'<div class="room-code">{code}</div>', unsafe_allow_html=True)
    with col_center:
        st.image(GITHUB_QR_URL, use_column_width=True)
    with col_right:
        participants = list(state["participants"].keys())
        st.markdown(f"<br><br>**{len(participants)} player(s)**", unsafe_allow_html=True)
        chips = "".join(f'<span class="participant-chip">{p}</span>' for p in participants)
        st.markdown(chips, unsafe_allow_html=True)

    st.markdown("---")
    status = state["status"]

    # Lobby
    if status == "lobby":
        st.markdown("### Waiting for players…")
        st.markdown("Share the room code above. Start when everyone has joined.")
        if participants and st.button("▶  Start Voting", use_container_width=True):
            start_voting(code)
            st.rerun()
        elif not participants:
            st.info("No participants yet.")
        time.sleep(3)
        st.rerun()

    # Voting
    elif status == "voting":
        st.markdown("### Voting in progress")
        state = load_state(code)
        if not state:
            st.error("Game state corrupted. Please refresh the page.")
            return
        total_p = len(state["participants"])
        voted_all = all_voted(state)

        # Show bracket visualization
        render_bracket_visualization(state, total_p)
        
        st.markdown("---")
        st.markdown("#### Live Vote Counts")
        
        for i, m in enumerate(state["matchups"]):
            if m["a"] is None or m["b"] is None:
                bye_q = m["b"] if m["a"] is None else m["a"]
                quote_text = bye_q.get('text', 'Unknown Quote') if isinstance(bye_q, dict) else str(bye_q)
                st.markdown(f"*Match {i+1}: BYE — \"{quote_text[:60]}\" advances*")
                continue
            va, vb = get_vote_counts(m)
            col_a, col_vs, col_b = st.columns([5, 1, 5])
            with col_a:
                render_quote_card(m["a"])
            with col_vs:
                st.markdown('<div class="vs-label" style="margin-top:2rem">vs</div>', unsafe_allow_html=True)
            with col_b:
                render_quote_card(m["b"])
            render_vote_bar(va, vb)
            st.markdown(f"<p style='font-size:0.78rem;color:#555;'>{va+vb}/{total_p} voted</p>", unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

        if voted_all:
            st.success("Everyone has voted!")
            if st.button("✅  End Voting & Show Results", use_container_width=True):
                advance_round(code)
                st.rerun()
        else:
            st.info("Waiting for all votes…")
        time.sleep(4)
        st.rerun()

    # Results
    elif status == "results":
        st.markdown("### Round Results")
        
        # Show bracket visualization
        render_bracket_visualization(state, len(state["participants"]))

        st.markdown("---")
        st.markdown("#### Results Summary")
        if state["bracket_history"]:
            last = state["bracket_history"][-1]
            for m in last:
                if m["a"] is None or m["b"] is None:
                    continue
                ws = m.get("winner", "a")
                winner, loser = m[ws], m["b" if ws == "a" else "a"]
                va, vb = get_vote_counts(m)
                wv, lv = (va, vb) if ws == "a" else (vb, va)
                author_str = f" — {winner['author']}" if winner.get('author') else ""
                st.markdown(f"""
                <div style="display:flex;gap:1rem;align-items:center;margin-bottom:0.6rem;">
                    <div style="flex:1;opacity:0.35;font-style:italic;font-size:0.88rem;">"{display_text(loser['text'])}"</div>
                    <div style="color:#4f8ef7;font-size:0.9rem;">→</div>
                    <div style="flex:1;font-style:italic;font-size:0.88rem;">
                        "{display_text(winner['text'])}"
                        <span style="font-size:0.75rem;color:#888;">{author_str} · {wv}-{lv}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown(f"**Next:** Round {state['round']} — {len(state['matchups'])} matchup(s)")
        if st.button("▶  Start Next Round", use_container_width=True):
            start_voting(code)
            st.rerun()

    # Done
    elif status == "done":
        champ = state.get("champion", {})
        champ_author_html = f'<div class="champion-author">— {champ["author"]}</div>' if champ.get("author") else ""
        st.markdown(f"""
        <div class="champion-card">
            <div class="champion-label">🏆 Champion</div>
            <div class="champion-quote">&#x201C;{champ.get('text','')}&#x201D;</div>
            {champ_author_html}
        </div>
        """, unsafe_allow_html=True)

        with st.expander("Full bracket history"):
            for r, rnd in enumerate(state["bracket_history"], 1):
                st.markdown(f"**Round {r}**")
                for m in rnd:
                    if not m["a"] or not m["b"]:
                        continue
                    ws = m.get("winner", "a")
                    w = m[ws]
                    va, vb = get_vote_counts(m)
                    wv = max(va, vb)
                    lv = min(va, vb)
                    author_str = f" — {w['author']}" if w.get('author') else ""
                    st.markdown(f'- ✓ *"{display_text(w["text"])}"*{author_str} ({wv}-{lv})')

        if st.button("🔄  New Game"):
            st.session_state.mode = None
            st.session_state.room_code = None
            st.rerun()


# ── PARTICIPANT VIEW ──────────────────────────────────────────────────────────
def page_participant():
    code = st.session_state.room_code
    name = st.session_state.player_name
    state = load_state(code)
    if not state:
        st.error("Game not found.")
        return

    # Heartbeat
    join_game(code, name)

    st.markdown("## [UN]Quotable - The Game")
    st.markdown(f"<p style='color:#555;'>Room <strong style='color:#888'>{code}</strong> · Playing as <strong style='color:#888'>{name}</strong></p>", unsafe_allow_html=True)
    st.markdown("---")

    status = state["status"]

    if status == "lobby":
        st.markdown("### Waiting for the host to start…")
        st.markdown("You're in! Hang tight.")
        time.sleep(3)
        st.rerun()

    elif status == "voting":
        st.markdown(f"### Round {state['round']} — Vote!")
        st.markdown("<p style='color:#666;font-size:0.88rem;'>Quotes are anonymous. Vote for whichever speaks to you.</p>", unsafe_allow_html=True)

        my_votes = get_player_votes(state, name)
        real = [m for m in state["matchups"] if m["a"] and m["b"]]
        st.markdown(f"<p style='font-size:0.8rem;color:#555;'>{len(my_votes)}/{len(real)} votes cast</p>", unsafe_allow_html=True)

        for i, m in enumerate(state["matchups"]):
            if not m["a"] or not m["b"]:
                continue
            my_pick = my_votes.get(i)
            st.markdown(f"**Match {i+1}**")
            col_a, col_vs, col_b = st.columns([5, 1, 5])
            with col_a:
                render_quote_card(m["a"], selected=(my_pick == "a"))
                btn_a = "✓ Your pick" if my_pick == "a" else "Vote for this"
                if st.button(btn_a, key=f"va_{i}", use_container_width=True):
                    cast_vote(code, i, name, "a")
                    st.rerun()
            with col_vs:
                st.markdown('<div class="vs-label" style="margin-top:2rem">vs</div>', unsafe_allow_html=True)
            with col_b:
                render_quote_card(m["b"], selected=(my_pick == "b"))
                btn_b = "✓ Your pick" if my_pick == "b" else "Vote for this"
                if st.button(btn_b, key=f"vb_{i}", use_container_width=True):
                    cast_vote(code, i, name, "b")
                    st.rerun()
            st.markdown("<br>", unsafe_allow_html=True)

        if len(my_votes) == len(real):
            st.success("All votes cast! Waiting for the host…")
        time.sleep(4)
        st.rerun()

    elif status == "results":
        st.markdown("### Results are in!")
        if state["bracket_history"]:
            for m in state["bracket_history"][-1]:
                if not m["a"] or not m["b"]:
                    continue
                ws = m.get("winner", "a")
                w = m[ws]
                va, vb = get_vote_counts(m)
                st.markdown(f'✓ *"{w["text"][:80]}"* — {max(va,vb)}-{min(va,vb)}')
        st.info("Waiting for host to start next round…")
        time.sleep(3)
        st.rerun()

    elif status == "done":
        champ = state.get("champion", {})
        champ_author_html = f'<div class="champion-author">— {champ["author"]}</div>' if champ.get("author") else ""
        st.markdown(f"""
        <div class="champion-card">
            <div class="champion-label">🏆 Champion</div>
            <div class="champion-quote">&#x201C;{champ.get('text','')}&#x201D;</div>
            {champ_author_html}
        </div>
        """, unsafe_allow_html=True)
        st.balloons()


# ── Router ────────────────────────────────────────────────────────────────────
mode = st.session_state.mode
if mode is None:
    page_landing()
elif mode == "host_setup":
    page_host_setup()
elif mode == "join_setup":
    page_join_setup()
elif mode == "host":
    page_host()
elif mode == "participant":
    page_participant()