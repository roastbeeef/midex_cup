import streamlit as st
import pandas as pd
import gspread
import datetime
from oauth2client.service_account import ServiceAccountCredentials
from collections import defaultdict
import re

# CONFIG
GOOGLE_SHEET_NAME = "midex_2025"
EVENT_TABS = {
    "May Stableford": "Standard Event",
    "Rover Medal": "Major",
    "June Medal": "Elevated Event",
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

EVENT_DATES = [
    "04/05/2025",
    "25/05/2025",
    "08/06/2025",
    "22/06/2025",
    "05/07/2025",
    "06/07/2025",
    "26/07/2025",
    "03/08/2025",
    "16/08/2025",
    "24/08/2025",
    "13/09/2025",
    "27/09/2025"
]

def parse_position(pos_str):
    """Extract numeric part from '1st', '2nd', '10th' etc."""
    if not isinstance(pos_str, str):
        return None
    match = re.match(r"^(\d+)", pos_str.strip())
    return int(match.group(1)) if match else None

@st.cache_data(ttl=300)
def load_all_event_data():
    all_data = {}
    for sheet_name in EVENT_TABS:
        try:
            df = load_event_results(sheet_name)
            all_data[sheet_name] = df
        except Exception as e:
            all_data[sheet_name] = pd.DataFrame(columns=["Position", "Name", "Score"])
            st.warning(f"⚠️ Failed to load {sheet_name}: {e}")
    return all_data

@st.cache_resource
def get_gsheet_client():
    creds_dict = dict(st.secrets["gcp_service_account"])
    if "\\n" in creds_dict["private_key"]:
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=300)
def load_eligible_player_names():
    client = get_gsheet_client()
    sheet = client.open(GOOGLE_SHEET_NAME).worksheet("entries")
    
    # Get all values from column A starting from row 2
    data = sheet.col_values(1)[1:]  # Skips the header (row 1)

    eligible_names = pd.Series(data).dropna().unique().tolist()  # Remove NaN and get unique names
    total_entries = len(eligible_names)  # Total entries are the count of unique names
    total_prize_fund = total_entries * 20  # Assuming £20 entry fee per player

    return [name.strip() for name in eligible_names], total_entries, total_prize_fund

@st.cache_data(ttl=300)
def load_event_results(sheet_name):
    client = get_gsheet_client()
    sheet = client.open(GOOGLE_SHEET_NAME).worksheet(sheet_name)
    data = sheet.get_all_values()

    # checks length of first row, if its less than 4, return empty dataframe
    if not data or len(data[0]) < 4:
        return pd.DataFrame(columns=["Position", "Name", "Score"])

    # iterate over the data
    results = []
    for row in data:
        try:
            name = row[0].strip()
            position = row[1].strip()
            score = row[3].strip()
            results.append((position, name, score))
        except (IndexError, ValueError):
            continue  # skip rows that don't conform

    if not results:
        return pd.DataFrame(columns=["Position", "Name", "Score"])

    df = pd.DataFrame(results, columns=["Position", "Name", "Score"])
    return df

def calculate_points(event_type, position):
    table = POINTS_TABLE.get(event_type, [])
    return table[position - 1] if 1 <= position <= len(table) else 0

def aggregate_points(event_data, entrants_list):
    player_points = defaultdict(int)
    event_breakdown = defaultdict(list)

    for sheet_name, label in EVENT_TABS.items():
        df = event_data.get(sheet_name, pd.DataFrame())
        if df.empty:
            continue

        for _, row in df.iterrows():
            name = row.get("Name", "").strip()
            pos_raw = row.get("Position", None)
            pos = parse_position(pos_raw)
            if pos is None:
                continue

            pts = calculate_points(label, pos)
            player_points[name] += pts
            event_breakdown[name].append((sheet_name, pts))

    if not player_points:
        return pd.DataFrame(columns=["Name", "Points", "Events"])

    leaderboard = pd.DataFrame([
        {"Name": name, "Points": points, "Events": event_breakdown[name]}
        for name, points in player_points.items() if name in entrants_list and points > 0
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

def df_to_html_table(df, header_color="#5E2CA5", header_text_color="white"):
    table_style = """
    <style>
    .responsive-table {
        width: 100%;
        overflow-x: auto;
        margin-bottom: 1em;
        border-collapse: collapse;
        font-family: 'Georgia', serif;
    }
    .responsive-table thead {
        background-color: """ + header_color + """;
        color: """ + header_text_color + """;
    }
    .responsive-table th, .responsive-table td {
        padding: 10px;
        border: 1px solid #ddd;
        text-align: center;
        white-space: nowrap;
    }
    .responsive-table tr:nth-child(even) {
        background-color: #f9f9f9;
    }
    </style>
    """

    html = table_style + "<div style='overflow-x:auto;'>"
    html += "<table class='responsive-table'><thead><tr>"
    for col in df.columns:
        html += f"<th>{col}</th>"
    html += "</tr></thead><tbody>"
    for _, row in df.iterrows():
        html += "<tr>"
        for item in row:
            html += f"<td>{item}</td>"
        html += "</tr>"
    html += "</tbody></table></div>"
    return html



st.set_page_config(page_title="MidEx Cup 2025", layout="wide")
st.markdown("""
<style>
    /* Base page style */
    .block-container {
        padding-top: 1rem;
        padding-bottom: 0rem;
    }

    /* Headline section */
    .midex-header {
        text-align: center;
        padding: 0.5rem 0 0.5rem 0;
        border-bottom: 2px solid #eee;
    }
    .midex-header h1 {
        font-size: 2.8rem;
        color:  #95a5a6;
        font-weight: 600;
        margin-bottom: 0;
        font-family: 'Segoe UI', sans-serif;
    }
    .midex-header span.orange {
        color: #FF6F00;
    }
    .midex-header span.purple {
        color: #5E2CA5;
    }
    .midex-header h4 {
        margin-top: 0.2rem;
        color: #666;
        font-weight: 400;
    }



    /* Metrics container */
    .metric-container .element-container {
        background-color: #f8f8f8;
        border: 1px solid #e0e0e0;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# -------------------- UI --------------------
st.markdown("""
<div class="midex-header">
    <h1>The<span class="purple">Mid</span><span class="orange">Ex</span>Cup</h1>
    <h4>2025 MSGC <i><b>Unofficial</b></i> Order of Merit</h4>
</div>
""", unsafe_allow_html=True)

entrants_list, entries, prize_pool = load_eligible_player_names()

event_data = load_all_event_data()
leaderboard_df = aggregate_points(event_data, entrants_list)
leaderboard_df["Position"] = leaderboard_df.index + 1


# entries = leaderboard_df["Name"].nunique()
leader_name = leaderboard_df.iloc[0]["Name"] if not leaderboard_df.empty else "TBD"
leader_points = leaderboard_df.iloc[0]["Points"] if not leaderboard_df.empty else 0

today = datetime.datetime.today()
event_dates_dt = [datetime.datetime.strptime(date, "%d/%m/%Y") for date in EVENT_DATES]
future_events = [(name, d) for (name, _), d in zip(EVENT_TABS.items(), event_dates_dt) if d >= today]
if future_events:
    next_event, next_date = future_events[0]
else:
    next_event, next_date = list(EVENT_TABS.keys())[0], EVENT_DATES[0]

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Total Entries", entries)
    st.caption(f"💰 Prize Pool: £{prize_pool}")
with col2:
    st.metric("Current Leader", leader_name)
    st.caption(f"🏆 {leader_points} points")
with col3:
    st.metric("Next Event", next_event)
    st.caption(f"📅 {next_date.strftime('%d %b %Y') if isinstance(next_date, datetime.datetime) else next_date}")

tabs = st.tabs(["📋 Rules / Entry", "🏆 Leaderboard", "📈 Event Results", "💯 Point Rewards Table"])

with tabs[0]:
    col_left, col_right = st.columns(2)
    with col_left:
        st.markdown("### ❓ What even is this?")
        st.markdown("""
        - The 2025 golf season features 12 official MidEx Cup events from **4th May to 27th Sept**.
        - Players can earn points based on their finishing position in each event, with an emphasis on winning or placing high.
        - Each event has a total number of points based on its profile - you can see how these are allocated in the points allocation table.
        - Only the **top 16** finishers earn points in each event.
        - At the end of the season, 1st place will earn 50% of the prize pool, 2nd place will earn 35% and 3rd place will earn 15%. 
        - *If there are more than 15 entries then 4th place will also be paid.*
        """)

    with col_right:
        st.markdown("### 🗳️ How can I enter?")
        st.markdown("""
        - Entry is £20, all of which will be paid out in prizes once the competition is finalised. 
        - You can join at any point during the season but will only earn points for events after your entry.
        - Entry can be confirmed by paying Matt Wilson the fine sum of £20, via:
            - [Monzo](https://monzo.me/mattwilson1)  
            - [PayPal](https://paypal.me/mattwilson1234)  
            - Bank transfer (📱 drop Matt a WhatsApp)  
            - Add credit to my pro shop account  
            - Or arrange to pay cash (pls no)
        """)

    st.markdown("### 🗓 Events")
    event_df = pd.DataFrame([
        {
            "Date": date,
            "Competition": name,
            "Type": label,
            "Points Allocation": POINTS_TABLE[label][0]
        }
        for date, (name, label) in zip(EVENT_DATES, EVENT_TABS.items())
    ])

    st.markdown(df_to_html_table(event_df), unsafe_allow_html=True)

with tabs[1]:
    st.subheader("📊 MidEx Leaderboard")
    top3 = leaderboard_df.head(3)
    col1, col2, col3 = st.columns(3)
    if len(top3) >= 1:
        with col1: st.metric(f"🥇 {top3.iloc[0]['Name']}", f"{int(top3.iloc[0]['Points'])} pts")
    if len(top3) >= 2:
        with col2: st.metric(f"🥈 {top3.iloc[1]['Name']}", f"{int(top3.iloc[1]['Points'])} pts")
    if len(top3) >= 3:
        with col3: st.metric(f"🥉 {top3.iloc[2]['Name']}", f"{int(top3.iloc[2]['Points'])} pts")
    
    styled_leaderboard(leaderboard_df[["Position", "Name", "Points"]])

with tabs[2]:
    st.subheader("🔍 Event Breakdown")
    if "selected_event" not in st.session_state:
        st.session_state.selected_event = list(EVENT_TABS.keys())[0]
        
    selected_event = st.selectbox("Select event", list(EVENT_TABS.keys()), index=list(EVENT_TABS.keys()).index(st.session_state.selected_event))
    st.session_state.selected_event = selected_event
    try:
        results_df = event_data.get(selected_event, pd.DataFrame())
        if results_df.empty:
            st.info("No results yet for this event.")
        else:
            st.markdown(df_to_html_table(results_df), unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"⚠️ Could not load results for {selected_event}. Error: {e}")


with tabs[3]:
    st.subheader("💯 Points Distribution")
    max_places = max(len(v) for v in POINTS_TABLE.values())
    places = list(range(1, max_places + 1))
    points_table_df = pd.DataFrame({"Place": places})
    for event_type, points in POINTS_TABLE.items():
        padded = points + [0] * (max_places - len(points))
        points_table_df[event_type] = padded
    st.markdown(df_to_html_table(points_table_df), unsafe_allow_html=True)
