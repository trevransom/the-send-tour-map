from flask import Flask, request, jsonify
import folium
from geopy.geocoders import Nominatim
import osmnx as ox
import networkx as nx
# Define function to get city coordinates
import folium
from folium import Popup, Tooltip
from itertools import cycle
import os
# Ok our goal is to map tour team movement and routes with highlights for each stop
# our input will be a datafram conttaining the city, # of responses, attendence #, date
# there will be multiple tour teams
# would be nice to have color coded routes for each team
# this is all in finland
import pandas as pd
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

# Initialize the DataFrame to hold tour data
tour_data = pd.DataFrame(columns=["City", "Team", "Responses", "Attendance", "Date"])
tour_data = pd.DataFrame({
    "City": ["Helsinki", "Espoo", "Tampere", "Helsinki", "Turku", "Oulu"],
    "Team": ["Team A", "Team A", "Team A", "Team B", "Team B", "Team B"],
    "Responses": [150, 200, 180, 300, 250, 120],
    "Attendance": [500, 450, 600, 700, 550, 500],
    "Date": ["2024-05-01", "2024-05-02", "2024-05-03", "2024-05-01", "2024-05-02", "2024-05-03"]
})


@app.route('/webhook', methods=['POST'])
def typeform_webhook():
    global tour_data
    data = request.json
    # Parse the Typeform response
    for response in data['form_response']['answers']:
        if response['type'] == 'text':  # Assuming text type for cities and teams
            city = response.get('text', '')
            team = response.get('team', '')
            responses = response.get('responses', 0)
            attendance = response.get('attendance', 0)
            date = response.get('date', '')

            # Append new data to the DataFrame
            new_entry = pd.DataFrame({
                "City": [city],
                "Team": [team],
                "Responses": [responses],
                "Attendance": [attendance],
                "Date": [date]
            })
            tour_data = pd.concat([tour_data, new_entry], ignore_index=True)
            # Call the function to generate the map after updating
    create_map()

    return jsonify({"status": "success"}), 200


@app.route('/mock_webhook', methods=['POST'])
def mock_typeform_webhook():
    global tour_data

    # Simulate incoming data
    mock_data = {
        "form_response": {
            "answers": [
                {"field": {"id": "city_field_id"}, "text": "Lahti"},
                {"field": {"id": "team_field_id"}, "text": "Team A"},
                {"field": {"id": "responses_field_id"}, "number": 10},
                {"field": {"id": "attendance_field_id"}, "number": 8},
                {"field": {"id": "date_field_id"}, "text": "2024-11-05"}
            ]
        }
    }

    # Process mock data
    for answer in mock_data["form_response"]["answers"]:
        if answer["field"]["id"] == "city_field_id":
            city = answer["text"]
        elif answer["field"]["id"] == "team_field_id":
            team = answer["text"]
        elif answer["field"]["id"] == "responses_field_id":
            responses = answer["number"]
        elif answer["field"]["id"] == "attendance_field_id":
            attendance = answer["number"]
        elif answer["field"]["id"] == "date_field_id":
            date = answer["text"]

    # Update DataFrame with the simulated data
    new_row = {
        "City": city,
        "Team": team,
        "Responses": responses,
        "Attendance": attendance,
        "Date": date
    }
    # tour_data = tour_data.append(new_row, ignore_index=True)
    new_df = pd.DataFrame([new_row])
    tour_data = pd.concat([tour_data, new_df], ignore_index=True)

    print(tour_data.head())
    # sys

    # Call the function to generate the map after updating
    create_map()

    return jsonify({"status": "success"}), 200


def create_map():
    global tour_data

    # Sample data

    print(tour_data.head())
    # Initialize geolocator
    geolocator = Nominatim(user_agent="tour_mapper")

    # Get coordinates for each city and add to the DataFrame
    tour_data["Coordinates"] = tour_data["City"].apply(lambda city: geolocator.geocode(city))
    tour_data["Latitude"] = tour_data["Coordinates"].apply(
        lambda loc: loc.latitude if loc else None)
    tour_data["Longitude"] = tour_data["Coordinates"].apply(
        lambda loc: loc.longitude if loc else None)
    tour_data.drop(columns="Coordinates", inplace=True)

    # Define color palette for each team
    colors = cycle(["blue", "green", "red", "purple", "orange", "darkred", "darkblue"])

    # Initialize map centered in Finland
    m = folium.Map(location=[64.0, 26.0], zoom_start=6)

    # Plot data for each team
    for team, color in zip(tour_data["Team"].unique(), colors):
        team_data = tour_data[tour_data["Team"] == team]

        # Plot each city stop with a marker
        for _, row in team_data.iterrows():
            tooltip = Tooltip(f"<b>{row['City']}</b> on {row['Date']}")
            popup = Popup(
                f"Team: {team}<br>City: {row['City']}<br>Date: {row['Date']}<br>"
                f"Responses: {row['Responses']}<br>Attendance: {row['Attendance']}",
                max_width=300
            )
            folium.Marker(
                location=[row["Latitude"], row["Longitude"]],
                tooltip=tooltip,
                popup=popup,
                icon=folium.Icon(color=color)
            ).add_to(m)

        # Draw route line connecting stops for each team
        route_coords = list(zip(team_data["Latitude"], team_data["Longitude"]))
        folium.PolyLine(
            route_coords,
            color=color,
            weight=2.5,
            opacity=0.8,
            tooltip=f"{team} Route"
        ).add_to(m)
    # Save the map to the static folder
    map_path = os.path.join('static', 'tour_map_finland.html')
    m.save(map_path)


@app.route('/map', methods=['GET'])
def serve_map():
    return send_from_directory('static', 'tour_map_finland.html')


if __name__ == '__main__':
    app.run(port=5000, debug=True)
