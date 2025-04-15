import streamlit as st
import pandas as pd
import gspread
import re
from oauth2client.service_account import ServiceAccountCredentials
from collections import defaultdict


# GLOBALS
GOOGLE_SHEET_NAME = "heronsdale_2025"

# Auth setup
@st.cache_resource
def get_gsheet_client():
    import json
    from oauth2client.service_account import ServiceAccountCredentials

    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

    # Load and manually fix private_key line breaks
    creds_dict = dict(st.secrets["gcp_service_account"])
    if "\\n" in creds_dict["private_key"]:
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

st.set_page_config(page_title="Heronsdale 2025 Side Action", layout="wide")

@st.cache_data(ttl=300)
def load_eligible_player_names():
    client = get_gsheet_client()
    sheet = client.open(GOOGLE_SHEET_NAME).worksheet("entries")
    data = sheet.get_all_values()
    df = pd.DataFrame(data[1:], columns=data[0])  # Skip header row
    eligible_names = df["Name"].dropna().unique().tolist()
    total_entries = df['total_entries'].astype(int).sum()
    total_prize_fund = df['total_paid'].astype(int).sum()
    return [name.strip() for name in eligible_names], total_entries, total_prize_fund


def styled_table(df):
    def highlight_top3(row):
        if row.name == 0:
            return ["background-color: #FFD700; font-weight: bold;"] * len(row)
        elif row.name == 1:
            return ["background-color: #C0C0C0; font-weight: bold;"] * len(row)
        elif row.name == 2:
            return ["background-color: #CD7F32; font-weight: bold;"] * len(row)
        else:
            return [""] * len(row)

    styled = (
        df.style
        .apply(highlight_top3, axis=1)
        .format(na_rep="", formatter={col: "{:.0f}" for col in df.columns if df[col].dtype in ['float64', 'int64']})
        .set_table_styles([
            {"selector": "th", "props": [("text-align", "center")]},
            {"selector": "td", "props": [("text-align", "center")]},
        ])
        .set_properties(**{
            "text-align": "center",
            "font-family": "Georgia",
            "font-size": "16px"
        })
        .hide(axis="index")
    )

    return st.markdown(styled.to_html(escape=False), unsafe_allow_html=True)



# Load round data from Google Sheets
def load_round_data(sheet_name, allowed_names=None):
    client = get_gsheet_client()
    sheet = client.open(GOOGLE_SHEET_NAME).worksheet(sheet_name)
    
    # Read all data
    data = sheet.get_all_values()
    
    if not data or not any(row for row in data if any(cell.strip() for cell in row)):
        return pd.DataFrame(columns=["Day", "Position", "Name", "Handicap", "Score"])

    cleaned_data = [row[:4] for row in data if len(row) >= 4]
    df = pd.DataFrame(cleaned_data, columns=["Day", "Position", "NameRaw", "Score"])
    df["Score"] = pd.to_numeric(df["Score"], errors="coerce")

    def split_name_handicap(name_raw):
        match = re.match(r"^(.*?)\((\d+)\)$", name_raw.strip())
        if match:
            return match.group(1).strip(), int(match.group(2))
        return name_raw.strip(), None

    df[["Name", "Handicap"]] = df["NameRaw"].apply(
        lambda x: pd.Series(split_name_handicap(x))
    )

    # Only keep players in the allowed list
    if allowed_names is not None:
        df = df[df["Name"].isin(allowed_names)]

    return df[["Day", "Position", "Name", "Handicap", "Score"]]


def calculate_places_paid(total_entries):
    base_places = 3
    max_places = 5
    extra_places = max(0, (total_entries - 30) // 10)
    return min(base_places + extra_places, max_places)

def clean_name(name):
    return name.split("(")[0].strip()

def get_main_leaderboard(dfs, side_pot_players):
    all_scores = defaultdict(list)

    # Collect scores from all round data
    for df in dfs:
        for _, row in df.iterrows():
            name = clean_name(row["Name"])
            score = row["Score"]
            if pd.notnull(score):
                all_scores[name].append(score)

    # Ensure all side pot players are included, even with no scores
    for name in side_pot_players:
        if name not in all_scores:
            all_scores[name] = []

    leaderboard = []
    for name in sorted(all_scores.keys()):
        scores = all_scores[name]
        scores.sort(reverse=True)
        best = scores[0] if len(scores) > 0 else 0
        second_best = scores[1] if len(scores) > 1 else 0
        leaderboard.append((name, best, second_best))

    df_leader = pd.DataFrame(leaderboard, columns=["Name", "Best Score", "Second Best"])
    df_leader = df_leader.sort_values(by=["Best Score", "Second Best"], ascending=False).reset_index(drop=True)
    df_leader["Position"] = df_leader.index + 1
    df_leader["Medal"] = df_leader["Position"].map({1: "🥇", 2: "🥈", 3: "🥉"}).fillna("")
    df_leader["Name"] = df_leader["Name"].apply(lambda x: f"<b>{x}</b>")
    return df_leader[["Position", "Medal", "Name", "Best Score", "Second Best"]]



def get_full_leaderboard(round_dfs, side_pot_players):
    # Combine all players from all rounds
    all_names = set()
    for df in round_dfs.values():
        all_names.update(df["Name"].unique())
    
    leaderboard_data = []

    for name in sorted(all_names):
        scores = []
        for day in ["day_1", "day_2", "day_3", "day_4"]:
            df = round_dfs[day]
            score = df.loc[df["Name"] == name, "Score"]
            scores.append(score.values[0] if not score.empty else None)

        # Best 2 sum
        best_two = sum(sorted([s for s in scores if s is not None], reverse=True)[:2])
        leaderboard_data.append((name, *scores, best_two))

    df_leader = pd.DataFrame(leaderboard_data, columns=["Name", "Round 1", "Round 2", "Round 3", "Round 4", "Best 2"])
    df_leader = df_leader.sort_values(by="Best 2", ascending=False).reset_index(drop=True)
    
    # Add bold formatting for side pot players
    def bold_name(name):
        return f"<b>{name}</b>" if name in side_pot_players else name

    df_leader["Name"] = df_leader["Name"].apply(bold_name)

    return df_leader

# Load all round data
round_names = ["day_1", "day_2", "day_3", "day_4"]
allowed_players, total_entries, total_prize_fund = load_eligible_player_names()

# entry vars
total_entries = int(total_entries)
places_paid = calculate_places_paid(total_entries)
round_dfs = {day: load_round_data(day, allowed_names=allowed_players) for day in round_names}


# ----------------------- Streamlit UI -----------------------

# Main UI layout
with st.container():
    # try:
    #     st.image(
    #         "https://upload.wikimedia.org/wikipedia/en/thumb/f/fd/Masters_Tournament_logo.svg/1920px-Masters_Tournament_logo.svg.png",
    #         use_container_width=True
    #     )
    # except:
    #     pass

    st.markdown("""
    <div style='text-align: center; padding: 0.5em 0 1em 0;'>
        <h1 style="
            color: #1A472A;
            font-family: Georgia, serif;
            font-size: 3.2em;
            margin-bottom: 0;
        ">The Heronsdale Hero</h1>
        <h4 style="
            color: #4F6022;
            font-family: Georgia, serif;
            margin-top: 0.2em;
        ">Heronsdale Side Pot - Single Best Round</h4>
    </div>
    """, unsafe_allow_html=True)

tabs = st.tabs(["🏆 Main", "🕹 Official Heronsdale Leaderboard"])

# Main Tab
with tabs[0]:
    # Entry metrics section
    col1, col2, col3 = st.columns(3)

    with col1:
        unique_players = len(set(allowed_players))
        st.metric("Total Entries", total_entries, help="Number of total score submissions")
        st.caption(f"👤 {unique_players} unique players")

    with col2:
        st.metric("Prize Pool", f"£{total_prize_fund}")
        st.caption(f"🏅 {places_paid} places paid")

    with col3:
        all_scores = pd.concat(round_dfs.values())
        leading_score = int(all_scores["Score"].max()) if not all_scores.empty else "N/A"
        st.metric("Leading Score", leading_score)
        st.caption("🥇 Best stableford score across all rounds")

    st.markdown("---")

    # Rules and Payment side by side
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("### 📜 Rules")
        st.markdown("""
        - Played over the **Heronsdale weekend (Easter BH)**   
        - Highest single round **Stableford** score counts toward the leaderboard  
        - **£5 per round entry fee**  
          - Must be paid **before** your round  
          - £20 if you enter all 4 rounds  
        - Rounds must be **WHS qualifiers** and **official Heronsdale entries** to qualify  
        - **3 places paid** (1st: 50%, 2nd: 35%, 3rd: 15%)  
          - One additional paid place for every 10 entries beyond 30 (up to 5 total)  
        - *Ties broken by comparing second best score & then CB on 2nd round*
        """)

    with col_right:
        st.markdown("### 📝 How do I sign up?")
        st.markdown("""
        Everyone is welcome, 
        just send **Matt Wilson** some money using one of the following methods:

        - [Monzo](https://monzo.me/mattwilson1)  
        - [PayPal](https://paypal.me/mattwilson1234)  
        - Bank transfer (📱 drop Matt a WhatsApp)  
        - Add credit to my pro shop account  
        - Or arrange to pay cash (pls no)

        ⚠️ *Entry must be confirmed before you play your round — no exceptions!*
        """)


    st.markdown("---")

    # Leaderboard table
    with st.container():
        st.markdown("## 🥇 Leaderboard")
        leaderboard = get_main_leaderboard(list(round_dfs.values()), allowed_players)
        if leaderboard.empty:
            st.info("No scores submitted yet.")
        else:
            styled_table(leaderboard)


# Side Competition (Blank)
with tabs[1]:
    st.markdown("## 🕹 Official Heronsdale Leaderboard")
    full_leaderboard = get_full_leaderboard(round_dfs, allowed_players)
    styled_table(full_leaderboard)

    