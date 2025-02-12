import pytz
from datetime import datetime, timedelta
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
JAWA_MAP_API_KEY = os.getenv("JAWA_MAP_API_KEY")


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
            "Attendance": fields.get("attendance"),  # this should be an int
            "Salvations": fields.get("salvations"),  # this should be an int
            "StartDate": fields.get("event_date"),
            "EndDate": fields.get("event_end_date"),
            "Church": fields.get("church"),
        }
        records.append(record)
    # sys

    # Create a DataFrame and convert it to JSON
    # Split the date ranges into start and end dates
    plan_data[['start_date', 'end_date']] = plan_data['Date'].str.split('-', expand=True)
    print(plan_data)
    # Convert start_date and end_date to datetime, handling missing values in end_date
    plan_data['start_date'] = pd.to_datetime(
        plan_data['start_date'],
        format='%d.%m.%Y', errors='coerce', utc=True)

    if len(records) > 0:
        typeform_df = pd.DataFrame(records)

        typeform_df['start_date'] = pd.to_datetime(
            typeform_df['StartDate'], format='mixed', utc=True)
        typeform_df['end_date'] = pd.to_datetime(typeform_df['EndDate'], format='mixed', utc=True)

        df = pd.concat([typeform_df, plan_data]).drop_duplicates(
            subset=['start_date', 'Team'],
            keep='first',
            ignore_index=True
        )
        df['Salvations'] = df['Salvations'].fillna(0).astype(int)
    else:
        df = plan_data
    df['end_date'] = pd.to_datetime(df['end_date'], format='%d.%m.%Y', errors='coerce', utc=True)
    # i need logic to sort by the first date if there's a span
    return df


def create_map(tour_data):
    geolocator = Nominatim(user_agent="tour_mapper")

    # Get coordinates for each city and add to the DataFrame
    #
    # print(city)
    tour_data["Coordinates"] = tour_data["City"].apply(
        lambda city: geolocator.geocode(city, timeout=10))
    tour_data["Latitude"] = tour_data["Coordinates"].apply(
        lambda loc: loc.latitude if loc else None)
    tour_data["Longitude"] = tour_data["Coordinates"].apply(
        lambda loc: loc.longitude if loc else None)
    tour_data.drop(columns="Coordinates", inplace=True)
    # tour_data
    # tour_data['Date'] = pd.to_datetime(tour_data['Date'], errors="coerce")
    print(tour_data)
    tour_data = tour_data[tour_data['start_date'] <= datetime.now(pytz.UTC) + timedelta(days=30)]
    print(tour_data)

    # Define color palette for each team
    red = "#fa0015"
    yellow = "#facf50"
    white = "#ffffff"
    blue = "#1d34be"
    violet = "#523d90"
    orange = "#f3724a"
    team_names = tour_data["Team"].unique().tolist()
    # ooo could we do gradients for these routes instead?
    send_colors = cycle([red, yellow, blue, white, violet, orange])

    team_colors = dict(zip(tour_data["Team"].unique(), send_colors))
    # first_team_name =

    # Initialize map centered in Finland
    # Free Option (lets test with this to save quota?)
    # what's our free option?
    # or do we wanna test quota?
    # yeah lets test... stress test...
    m = folium.Map(location=[64.0, 26.0], tiles=None, zoom_start=5)

    # Quota Options
    folium.TileLayer(
        tiles="https://{{s}}.tile.jawg.io/jawg-dark/{{z}}/{{x}}/{{y}}{{r}}.png?access-token={JAWA_MAP_API_KEY}".format(
            JAWA_MAP_API_KEY=JAWA_MAP_API_KEY),
        attr="&copy; Esri &mdash; Source: Esri, USGS, NOAA",
        control=False).add_to(m)

    # city_visit_counts = tour_data.groupby('City')['Team'].nunique().reset_index(name='team_count')
    city_visit_counts = tour_data.groupby('City').size().reset_index(name="team_count")
    # team_counts = df.groupby("City").size().reset_index(name="TeamOccurrences")
    # print()
    # ah i see this is only account for other teams not within its own team
    # it should both account for its own team AND other teams - so like the whole list basically
    print(city_visit_counts)

    # Filter for cities visited by more than one team
    # multiple_team_cities = city_visit_counts[city_visit_counts['team_count'] > 1]
    # multiple_visit_list = multiple_team_cities["City"].tolist()
    multiple_visit_list = city_visit_counts[city_visit_counts["team_count"] > 1]["City"].tolist(
    )
    print(multiple_visit_list)

    # Feature Groups
#    past_events = folium.FeatureGroup(name="Past Events", overlay=True)
#    upcoming_events = folium.FeatureGroup(name="Upcoming Events", overlay=True)

    OFFSET = 0.03
    # Group by team and plot routes
    for team_index, (team, team_data) in enumerate(tour_data.groupby("Team")):
        # Sort cities by date to draw lines in order of travel
        team_data = team_data.sort_values("start_date")
        route_coords = []
        # fg = folium.FeatureGroup(
        #    name=team, overlay=True, show=True
        #    if team == team_names[0] else False)

        fg = folium.FeatureGroup(name=team, overlay=True, show=True)

        # Add markers for each stop, offsetting if necessary
        for i, (_, row) in enumerate(team_data.iterrows()):
            frand = 0
            IN_FUTURE = True if row['start_date'] > datetime.now(pytz.utc) else False

            if row["City"] in multiple_visit_list:
                frand = random.uniform(0, OFFSET)

            print(team, i, row["City"], row["start_date"], frand, frand * (team_index + 1))
            offset_lat = row["Latitude"]
            # doesn't work if team index is 0
            offset_lon = row["Longitude"] - frand * (team_index + 1)
            route_coords.append([offset_lat, offset_lon])
            if i > 0:
                route_coords_sub = [route_coords[i-1], route_coords[i]]
                line_style = '5, 5' if IN_FUTURE else None
                # print(line_style)
                route = folium.PolyLine(
                    route_coords_sub,
                    color=team_colors[team],
                    dash_array=line_style,
                    weight=1,
                    opacity=1,
                    tooltip=f"{team} reitti"
                ).add_to(fg)

                print(f"team-{team.replace(' ', '-')}")

            # need to join the dates here if here
            dates = f"""{row['start_date'].strftime(
                '%Y-%m-%d')}{' - '+row['end_date'].strftime('%Y-%m-%d') if pd.notnull(row['end_date']) else ''}"""
            marker_text = f"""
                <b>Kaupunki:</b> {row['City']}
                <br>
                <b>Paikka:</b> {row['Church']}
                <br>
                <b>Tiimi:</b> {row['Team']}
                <br>
            """

            if pd.notnull(row['end_date']):
                marker_text += f"""
                    <b>Aloituspäivä:</b> {row['start_date'].strftime('%Y-%m-%d') if pd.notnull(row['start_date']) else "-"}
                    <br>
                    <b>Päättymispäivä:</b> {row['end_date'].strftime('%Y-%m-%d') if pd.notnull(row['end_date']) else "-"}
                    <br>
                """
            else:
                marker_text += f"""
                    <b>Päivä:</b> {row['start_date'].strftime('%Y-%m-%d') if pd.notnull(row['start_date']) else "-"}
                    <br>
                """

            if pd.notnull(row.get('Attendance')) and not IN_FUTURE:
                marker_text += f"""
                    <b>Osallistujien määrä:</b> {int(row['Attendance'])}<br>
                """

            if int(row.get("Salvations")) > 0 and not IN_FUTURE:
                print(row['Salvations'])
                marker_text += f"""
                    <b>Uskoontulleiden määrä:</b> {int(row['Salvations'])}<br>
                """

            # Place a fire emoji marker for each stop
            mark = folium.Marker(
                location=[offset_lat, offset_lon],
                popup=folium.Popup(marker_text, max_width=250),
                id=team,
                icon=folium.DivIcon(
                    html=(
                        f'<div id="{team}" style="font-size:24px; color:red; text-align:center; '
                        'transform: translate(-50%, -50%);">🔥</div>'
                    )
                )
            ).add_to(fg)

        fg.add_to(m)
        # Add Groups to Map

    # Save the map to the static folder
    # Add a legend to the map
    legend_html = '''
    <div style="
    position: absolute; 
    bottom: 130px; left: 10px; width: auto; max-width: 200px; height: auto; 
    background-color: white; z-index:9999; font-size:12px;
    border:2px solid grey; border-radius: 8px; padding: 10px;
    box-shadow: 2px 2px 6px rgba(0,0,0,0.3);">
    <strong>Legenda</strong><br>
    <div style="display: flex; align-items: center; margin-top: 5px;">
        <svg width="30" height="8">
            <line x1="0" y1="4" x2="30" y2="4" style="stroke:#0275ff;stroke-width:3;stroke-dasharray:5,5" />
        </svg> 
        <span style="margin-left: 8px;">Tulossa</span>
    </div>
    <div style="display: flex; align-items: center; margin-top: 5px;">
        <svg width="30" height="8">
            <line x1="0" y1="4" x2="30" y2="4" style="stroke:#0275ff;stroke-width:3" />
        </svg> 
        <span style="margin-left: 8px;">Edellinen</span>
    </div>
    </div>
    
    '''
    # Add LayerControl for toggling
    folium.LayerControl(position="bottomleft", collapsed=False).add_to(m)

    m.get_root().html.add_child(folium.Element(legend_html))
    m.save("static/map.html")


tour_plan_data = fetch_advance_data()
# print(tou)
# sys
results = fetch_typeform_data()
tour_data = process_data(results, tour_plan_data)
create_map(tour_data)
