import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from collections import defaultdict

# CONFIG
GOOGLE_SHEET_NAME = "midex_2025"
EVENT_TABS = {
    "May Stableford": "Standard Event",
    "May Medal": "Elevated Event",
    "Rover Medal": "Major",
    "Stableford Handicap Trophy": "Major",
    "Club Championships (r1)": "Playoff Event",
    "Club Championships (r2)": "Playoff Event",
    "July Stableford": "Standard Event",
    "August Stableford (Red Tee)": "Standard Event",
    "August Medal": "Elevated Event",
    "August Stableford": "Standard Event",
    "Mid Sussex Masters": "Major",
    "September Stableford": "Standard Event"
}

POINTS_TABLE = {
    "Standard Event": [300, 180, 114, 81, 66, 60, 54, 51, 48, 45, 42, 39, 36, 34, 33, 32],
    "Elevated Event": [550, 330, 209, 149, 121, 110, 99, 94, 88, 83, 77, 72, 66, 63, 61, 58],
    "Major": [750, 450, 285, 203, 165, 150, 135, 128, 120, 113, 105, 98, 90, 86, 83, 80],
    "Playoff Event": [1200, 720, 456, 324, 264, 240, 216, 204, 192, 180, 168, 156, 144, 137, 132, 127],
}

# Streamlit Config
st.set_page_config(page_title="The MidEx Cup 2024", layout="wide")

@st.cache_resource
def get_gsheet_client():
    creds_dict = dict(st.secrets["gcp_service_account"])
    if "\\n" in creds_dict["private_key"]:
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=300)
@st.cache_data(ttl=300)
def load_event_results(sheet_name):
    client = get_gsheet_client()
    sheet = client.open(GOOGLE_SHEET_NAME).worksheet(sheet_name)
    data = sheet.get_all_values()

    if not data:
        return pd.DataFrame(columns=["Position", "Name"])

    # Assume first column = Name, second column = Position
    df = pd.DataFrame([row[:2] for row in data], columns=["Name", "Position"])
    df["Position"] = pd.to_numeric(df["Position"], errors="coerce")
    df = df.dropna(subset=["Position"])
    df["Position"] = df["Position"].astype(int)
    df["Name"] = df["Name"].str.strip()
    return df.sort_values("Position")


def calculate_points(event_type, position):
    table = POINTS_TABLE.get(event_type, [])
    return table[position - 1] if 1 <= position <= len(table) else 0

def aggregate_points():
    player_points = defaultdict(int)
    event_breakdown = defaultdict(list)

    for sheet_name, label in EVENT_TABS.items():
        try:
            df = load_event_results(sheet_name)
        except Exception as e:
            st.warning(f"⚠️ Could not load event: {sheet_name}. Error: {e}")
            continue

        for _, row in df.iterrows():
            name = row.get("Name", "").strip()
            pos = row.get("Position", None)

            if pd.isna(pos) or not isinstance(pos, int):
                continue

            pts = calculate_points(label, pos)
            player_points[name] += pts
            event_breakdown[name].append((sheet_name, pts))

    if not player_points:
        return pd.DataFrame(columns=["Name", "Points", "Events"])

    leaderboard = pd.DataFrame([
        {"Name": name, "Points": points, "Events": event_breakdown[name]}
        for name, points in player_points.items()
    ])
    return leaderboard.sort_values("Points", ascending=False).reset_index(drop=True)


def styled_leaderboard(df):
    def highlight(row):
        if row.name == 0:
            return ["background-color: #FFD700; font-weight: bold;"] * len(row)
        elif row.name == 1:
            return ["background-color: #C0C0C0; font-weight: bold;"] * len(row)
        elif row.name == 2:
            return ["background-color: #CD7F32; font-weight: bold;"] * len(row)
        else:
            return [""] * len(row)

    df_styled = (
        df.style
        .apply(highlight, axis=1)
        .format({"Points": "{:,.0f}"})
        .set_properties(**{"text-align": "center", "font-family": "Georgia", "font-size": "16px"})
        .hide(axis="index")
    )
    return st.markdown(df_styled.to_html(escape=False), unsafe_allow_html=True)

# -------------------- UI --------------------
st.markdown("""
    <div style='text-align: center; padding: 0.5em 0;'>
        <h1 style='color: #5E2CA5; font-size: 3em; font-family: Georgia;'>The <span style='color:#FF6F00;'>MidEx</span> Cup</h1>
        <h4 style='color: #444;'>2025 (unofficial) Order of Merit</h4>
    </div>
""", unsafe_allow_html=True)

tabs = st.tabs(["📋 Rules / Entry", "🏆 Leaderboard", "📈 Event Results"])

with tabs[1]:
    leaderboard_df = aggregate_points()
    leaderboard_df["Position"] = leaderboard_df.index + 1

    # Top 3 metrics
    top3 = leaderboard_df.head(3)

    col1, col2, col3 = st.columns(3)
    if len(top3) >= 1:
        with col1:
            st.metric(label=f"🥇 {top3.iloc[0]['Name']}", value=f"{int(top3.iloc[0]['Points'])} pts")
    if len(top3) >= 2:
        with col2:
            st.metric(label=f"🥈 {top3.iloc[1]['Name']}", value=f"{int(top3.iloc[1]['Points'])} pts")
    if len(top3) >= 3:
        with col3:
            st.metric(label=f"🥉 {top3.iloc[2]['Name']}", value=f"{int(top3.iloc[2]['Points'])} pts")

    st.markdown("### 🏁 Current Standings")
    display_df = leaderboard_df[["Position", "Name", "Points"]]
    styled_leaderboard(display_df)


with tabs[0]:
    col_left, col_middle, col_right = st.columns(3)

    with col_left:
        st.markdown("### ❓ What even is this?")
        st.markdown("""
        - The 2025 golf season features 12 official MidEx Cup events from **4th May to 27th Sept**.
        - Tour members can earn points based on their finishing position in each event, with an emphasis on wins and high places.
        - Each event has a total number of points based on its profile - you can see how these are allocated in the table below.
        - Only the **top 16** finishers earn points in each event.
        """)

    with col_middle:
        st.markdown("### 🗳️ How can I enter?")
        st.markdown("""
        - Tour membership is £20, all of which will be paid out in prizes once the competition is finalised. 
        - You can join at any point during the season but will only earn points for events after your entry.
        - Entry can be confirmed by paying Matt Wilson £20, via:
            - [Monzo](https://monzo.me/mattwilson1)  
            - [PayPal](https://paypal.me/mattwilson1234)  
            - Bank transfer (📱 drop Matt a WhatsApp)  
            - Add credit to my pro shop account  
            - Or arrange to pay cash (pls no)
        """)

    with col_right:
        st.markdown("### 💰 What can I win?")
        st.markdown("""
        - 1st place will earn 50%, 2nd place will earn 35% and 3rd place will earn 15%.
        - There are currently x players registered, with a total prize pool of:
        - The current payounts are:
            - 1st:
            - 2nd:
            - 3rd:
        """)

    st.markdown("### 🗓 Events")
    event_df = pd.DataFrame([
        {"Date": date, "Competition": name, "Label": label}
        for date, (name, label) in zip([
            "05/05/2024", "19/05/2024", "08/06/2024", "23/06/2024", 
            "06/07/2024", "07/07/2024", "21/07/2024", "04/08/2024",
            "10/09/2024", "18/09/2024", "15/09/2024", "29/09/2024"
        ], EVENT_TABS.items())
    ])
    st.dataframe(event_df, use_container_width=True)

    st.markdown("### 🧮 Points Distribution Table")

    # Create and show the points distribution
    max_places = max(len(v) for v in POINTS_TABLE.values())
    places = list(range(1, max_places + 1))
    
    points_table_df = pd.DataFrame({"Place": places})

    for event_type, points in POINTS_TABLE.items():
        padded = points + [0] * (max_places - len(points))  # Fill with 0s
        points_table_df[event_type] = padded

    st.dataframe(points_table_df, use_container_width=True)


with tabs[2]:
    st.markdown("### 🔍 Individual Event Results")
    selected_event = st.selectbox("Select an event", list(EVENT_TABS.keys()))
    event_type = EVENT_TABS[selected_event]
    results_df = load_event_results(selected_event)
    results_df["Points"] = results_df["Position"].apply(lambda pos: calculate_points(event_type, pos))
    st.dataframe(results_df, use_container_width=True)
