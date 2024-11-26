import pytz
import folium
import random
from geopy.geocoders import Nominatim
import folium
from folium import Popup, Tooltip
from itertools import cycle
import os
import pandas as pd
import requests
from io import BytesIO

random.seed(0)

TYPEFORM_API_KEY = os.getenv("TYPEFORM_API_KEY")
TYPEFORM_FORM_ID = os.getenv("TYPEFORM_FORM_ID")
TENANT_ID = os.getenv("TENANT_ID")
MICROSOFT_GRAPH_VALUE = os.getenv("MICROSOFT_GRAPH_VALUE")
MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID")
TOUR_DATA_ONEDRIVE_URL = os.getenv("TOUR_DATA_ONEDRIVE_URL")


# need to fetch the excel from onedrive now
# URL to get the access token
token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"

# Data required for the token request
data = {
    'grant_type': 'client_credentials',
    'client_id': MICROSOFT_CLIENT_ID,
    'client_secret': MICROSOFT_GRAPH_VALUE,
    'scope': 'https://graph.microsoft.com/.default'
}

# Send the POST request to get the token
response = requests.post(token_url, data=data)
response_data = response.json()
access_token = response_data.get('access_token')


def fetch_advance_data():
    # df = pd.read_excel("./data/TOUR TEAM PLAN.xlsx", sheet_name=None)
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Cache-Control': 'no-cache'
    }
    response = requests.get(TOUR_DATA_ONEDRIVE_URL, headers=headers)

    file_content = BytesIO(response.content)
    # df_dict = pd.read_excel(file_content, sheet_name=None#)
    df = pd.read_excel(file_content, sheet_name=None)

    all_sheets = []
    list_names = []
    for name, sheet in df.items():
        sheet['Team'] = name
        list_names.append(name)
        sheet = sheet.rename(columns=lambda x: x.split('\n')[-1])
        all_sheets.append(sheet)

    df = pd.concat(all_sheets)
    return df


def fetch_typeform_data():
    url = f"https://api.typeform.com/forms/{TYPEFORM_FORM_ID}/responses"
    headers = {
        "Authorization": f"Bearer {TYPEFORM_API_KEY}"
    }
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print("Failed to fetch data:", response.status_code, response.text)
        return None

    data = response.json()
    return data['items']


def process_data(data, plan_data):
    # make sure the data upserts teh plan data
    # Example: Extract city, responses, attendance, date, and team from Typeform responses
    records = []
    for item in data:
        fields = {ans["field"]["ref"]: ans[ans["type"]] for ans in item['answers']}
        # lets format the event date here too

        record = {
            # "email": fields.get("email"),
            "City": fields.get("city"),
            "Team": fields.get("tour_team"),
            "Recap": fields.get("recap"),
            "Attendance": fields.get("attendance"),
            "Date": fields.get("event_date"),
            "Church": fields.get("church"),
        }
        records.append(record)

    # Create a DataFrame and convert it to JSON
    typeform_df = pd.DataFrame(records)
    typeform_df['Date'] = pd.to_datetime(typeform_df['Date'], format='mixed', utc=True)
    plan_data['Date'] = pd.to_datetime(plan_data['Date'], format='mixed', utc=True)

    df = pd.concat([typeform_df, plan_data]).drop_duplicates(
        subset=['Date', 'Team'],
        keep='first',
        ignore_index=True
    )
    return df


def create_map(tour_data):
    geolocator = Nominatim(user_agent="tour_mapper")

    # Get coordinates for each city and add to the DataFrame
    tour_data["Coordinates"] = tour_data["City"].apply(lambda city: geolocator.geocode(city))
    tour_data["Latitude"] = tour_data["Coordinates"].apply(
        lambda loc: loc.latitude if loc else None)
    tour_data["Longitude"] = tour_data["Coordinates"].apply(
        lambda loc: loc.longitude if loc else None)
    tour_data.drop(columns="Coordinates", inplace=True)
    from datetime import datetime, timedelta
    # tour_data
    # tour_data['Date'] = pd.to_datetime(tour_data['Date'], errors="coerce")
    print(tour_data)
    tour_data = tour_data[tour_data['Date'] <= datetime.now(pytz.UTC) + timedelta(days=30)]
    print(tour_data)

    # Define color palette for each team
    colors = cycle(["blue", "green", "red", "purple", "orange", "darkred", "darkblue"])
    red = "#fa0015"
    yellow = "#facf50"
    # ooo could we do gradients for these routes instead?
    send_colors = cycle([red, yellow, "#1d34be"])

    team_colors = dict(zip(tour_data["Team"].unique(), send_colors))

    # Initialize map centered in Finland
    m = folium.Map(location=[64.0, 26.0], tiles="Cartodb Positron", zoom_start=6)

    city_visit_counts = tour_data.groupby('City')['Team'].nunique().reset_index(name='team_count')

    # Filter for cities visited by more than one team
    multiple_team_cities = city_visit_counts[city_visit_counts['team_count'] > 1]
    multiple_visit_list = multiple_team_cities["City"].tolist()

    OFFSET = 0.03

    # Group by team and plot routes
    for team_index, (team, team_data) in enumerate(tour_data.groupby("Team")):
        # Sort cities by date to draw lines in order of travel
        team_data = team_data.sort_values("Date")
        route_coords = []

        # Add markers for each stop, offsetting if necessary
        for i, (_, row) in enumerate(team_data.iterrows()):
            frand = 0
            IN_FUTURE = True if row['Date'] > datetime.now(pytz.utc) else False

            if row["City"] in multiple_visit_list:
                frand = random.uniform(0, OFFSET)

            print(team, i, row["City"], frand * team_index)
            offset_lat = row["Latitude"]
            offset_lon = row["Longitude"] - frand * team_index
            route_coords.append([offset_lat, offset_lon])
            if i > 0:
                route_coords_sub = [route_coords[i-1], route_coords[i]]
                line_style = '5, 5' if IN_FUTURE else None
                print(line_style)
                # folium.PolyLine(segment_coords, color=color, weight=5, opacity=0.8).add_to(m)
                folium.PolyLine(
                    route_coords_sub,
                    color=team_colors[team],
                    dash_array=line_style,
                    weight=3,
                    opacity=1,
                    tooltip=f"{team} reitti"
                ).add_to(m)

            marker_text = f"""
                <b>City:</b> {row['City']}

                <br>
                <b>Team:</b> {row['Team']}

                <br>
                <b>Date:</b> {row['Date'].strftime('%Y-%m-%d')
                              if pd.notnull(row['Date']) else "Date not available"}
            """

            if not IN_FUTURE:
                marker_text += f"""
                    <br><b>Responses:</b> {row['Recap']}<br>
                    <b>Attendance:</b> {row['Attendance']}<br>
                """

            # Place a fire emoji marker for each stop
            folium.Marker(
                location=[offset_lat, offset_lon],
                popup=folium.Popup(marker_text, max_width=250),
                # tooltip=folium.Tooltip(marker_text, ),
                # icon=folium.Icon(color="orange", icon="fire", prefix='fa')
                # icon=folium.DivIcon(
                #    icon_size=(20, 20),
                #    html='<div style="font-size: 20px;">🔥</div>'
                # )
                icon=folium.DivIcon(
                    html=(
                        '<div style="font-size:24px; color:red; text-align:center; '
                        'transform: translate(-50%, -50%);">🔥</div>'
                    )
                )
            ).add_to(m)

    # Save the map to the static folder
    # Add a legend to the map
    legend_html = '''
    <div style="
    position: fixed; 
    bottom: 10%; left: 5%; width: auto; max-width: 250px; height: auto; 
    background-color: white; z-index:9999; font-size:16px;
    border:2px solid grey; border-radius: 8px; padding: 15px;
    box-shadow: 2px 2px 6px rgba(0,0,0,0.3);">
    <strong>Legend</strong><br>
    <div style="display: flex; align-items: center; margin-top: 5px;">
        <svg width="30" height="8">
            <line x1="0" y1="4" x2="30" y2="4" style="stroke:blue;stroke-width:3;stroke-dasharray:5,5" />
        </svg> 
        <span style="margin-left: 8px;">Future Route</span>
    </div>
    <div style="display: flex; align-items: center; margin-top: 5px;">
        <svg width="30" height="8">
            <line x1="0" y1="4" x2="30" y2="4" style="stroke:blue;stroke-width:3" />
        </svg> 
        <span style="margin-left: 8px;">Past Route</span>
    </div>
    </div>
    '''

    m.get_root().html.add_child(folium.Element(legend_html))
    m.save("static/map.html")


tour_plan_data = fetch_advance_data()
# print(tou)
# sys
results = fetch_typeform_data()
tour_data = process_data(results, tour_plan_data)
create_map(tour_data)
