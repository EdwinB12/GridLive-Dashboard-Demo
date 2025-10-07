import streamlit as st
import requests
import pandas as pd
import folium
from streamlit_folium import st_folium
from pyproj import Transformer
import plotly.express as px
import json
from datetime import datetime, timedelta

# Page configuration
st.set_page_config(page_title="GridLive API Dashboard", page_icon="⚡", layout="wide")

# Title
st.title("⚡ GridLive API Dashboard")

# API Configuration
BASE_URL = "https://api.gridlive.shef.ac.uk"


# Load API key
@st.cache_data
def load_api_key():
    """Load API key from .streamlit/secrets.toml"""
    try:
        return st.secrets["GRIDLIVE_API_TOKEN"]
    except Exception as e:
        st.error(f"Error loading API key from secrets.toml: {str(e)}")
        return None


API_KEY = load_api_key()


# Function to fetch list of license areas
@st.cache_data(ttl=3600)
def fetch_license_areas():
    """
    Fetch list of all license areas from GridLive API

    Returns:
        List of license area names
    """
    url = f"{BASE_URL}/license_area"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        # Extract unique license area names
        license_areas = [item["license_area_name"] for item in data]
        return sorted(license_areas)
    except Exception as e:
        st.error(f"Error fetching license areas: {str(e)}")
        return []


# Function to fetch ESA metadata from the API
@st.cache_data(ttl=3600)
def fetch_esa_metadata(limit=None, license_areas=None):
    """
    Fetch ESA (Electricity Supply Area) metadata from GridLive API

    Args:
        limit: Number of records to fetch per license area (None for all)
        license_areas: List of license area names to filter by (None for all)

    Returns:
        DataFrame with ESA metadata
    """
    all_data = []

    if license_areas and len(license_areas) > 0:
        # Fetch data for each selected license area
        for license_area in license_areas:
            url = f"{BASE_URL}/esa_metadata/license_area/{license_area}"
            params = {}
            if limit:
                params["limit"] = limit

            try:
                response = requests.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                all_data.extend(data)
            except Exception as e:
                st.error(f"Error fetching data for {license_area}: {str(e)}")

        if all_data:
            return pd.DataFrame(all_data)
        else:
            return pd.DataFrame()
    else:
        # Fetch all data if no license areas specified
        url = f"{BASE_URL}/esa_metadata/"
        params = {}
        if limit:
            params["limit"] = limit

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            df = pd.DataFrame(data)
            return df
        except Exception as e:
            st.error(f"Error fetching data: {str(e)}")
            return pd.DataFrame()


# Function to convert British National Grid coordinates to lat/lon
@st.cache_data
def convert_coords_to_latlon(eastings, northings):
    """
    Convert British National Grid (EPSG:27700) coordinates to WGS84 (lat/lon)

    Args:
        eastings: Eastings coordinate
        northings: Northings coordinate

    Returns:
        Tuple of (latitude, longitude)
    """
    # Create transformer from British National Grid (EPSG:27700) to WGS84 (EPSG:4326)
    transformer = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(eastings, northings)
    return lat, lon


# Function to fetch smart meter data for a specific ESA
def fetch_smart_meter_data(esa_id, start_datetime=None, end_datetime=None):
    """
    Fetch smart meter data for a specific ESA

    Args:
        esa_id: The ESA ID to fetch data for
        start_datetime: Start datetime in ISO format (default: 30 days ago)
        end_datetime: End datetime in ISO format (default: now)

    Returns:
        DataFrame with smart meter data
    """
    if not API_KEY:
        st.error("API key not available")
        return pd.DataFrame()

    # Set default date range if not provided
    if not end_datetime:
        end_datetime = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+00:00")
    if not start_datetime:
        start_date = datetime.now() - timedelta(days=30)
        start_datetime = start_date.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    url = f"{BASE_URL}/smart_meter/esa/{esa_id}"
    headers = {"Authorization": API_KEY}
    params = {"start_datetime": start_datetime, "end_datetime": end_datetime}

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        if data:
            return pd.DataFrame(data)
        else:
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Error fetching smart meter data for ESA {esa_id}: {str(e)}")
        return pd.DataFrame()


# Sidebar controls
st.sidebar.header("Settings")

# Fetch available license areas
available_license_areas = fetch_license_areas()

if available_license_areas:
    # License area multi-select
    selected_license_areas = st.sidebar.multiselect(
        "Select License Areas",
        options=available_license_areas,
        default=[],
        help="Select one or more license areas to filter substations. Leave empty to show all.",
    )
else:
    selected_license_areas = []
    st.sidebar.warning("Could not load license areas")

# Number of ESAs per license area limit
data_limit = st.sidebar.number_input(
    "ESAs per license area",
    min_value=0,
    max_value=10000,
    value=500,
    step=100,
    help="Number of ESAs to load per selected license area (0 for unlimited). Higher values may take longer to load.",
)

# Convert 0 to None for unlimited
limit_value = None if data_limit == 0 else data_limit

# Fetch data
with st.spinner("Fetching data from GridLive API..."):
    metadata_df = fetch_esa_metadata(
        limit=limit_value,
        license_areas=selected_license_areas if selected_license_areas else None,
    )

if not metadata_df.empty:
    # Calculate statistics
    num_unique_substations = metadata_df["secondary_substation_id"].nunique()
    num_esas = len(metadata_df)

    st.sidebar.success(
        f"Loaded {num_esas} ESAs from {num_unique_substations} substations"
    )

    # Show selected license areas info
    if selected_license_areas:
        st.sidebar.info(f"**Selected areas:** {', '.join(selected_license_areas)}")

    # Convert coordinates
    with st.spinner("Converting coordinates..."):
        # Groupby secondary_substation_id and get number of rows
        metadata_df["number_of_feeders"] = metadata_df.groupby(
            "secondary_substation_id"
        )["secondary_substation_id"].transform("count")

        # Create display dataframe with unique substations
        df = metadata_df.drop_duplicates(
            subset=["esa_location_eastings", "esa_location_northings"]
        )

        df[["latitude", "longitude"]] = df.apply(
            lambda row: pd.Series(
                convert_coords_to_latlon(
                    row["esa_location_eastings"], row["esa_location_northings"]
                )
            ),
            axis=1,
        )

    # Create two-column layout
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("UK Substation Locations")
        st.write("Click on a substation to view smart meter data")

        # Create map centered on UK
        m = folium.Map(
            location=[54.5, -2.0],  # Center of UK
            zoom_start=6,
            tiles="OpenStreetMap",
        )

        # Add markers for each substation
        for idx, row in df.iterrows():
            folium.CircleMarker(
                location=[row["latitude"], row["longitude"]],
                radius=4,
                popup=folium.Popup(
                    f"""<b>{row["secondary_substation_name"]}</b><br>
                    Secondary Substation ID: {row["secondary_substation_id"]}<br>
                    DNO: {row["dno_name"]}<br>
                    License Area: {row["license_area_name"]}<br>
                    Number of Feeders: {row["number_of_feeders"]}""",
                    max_width=300,
                ),
                tooltip=row["secondary_substation_name"],
                color="blue",
                fill=True,
                fillOpacity=0.7,
            ).add_to(m)

        # Display map and capture click data
        map_data = st_folium(m, width=700, height=600)

    with col2:
        st.subheader("Smart Meter Data")

        # Check if a marker was clicked
        if map_data and map_data.get("last_object_clicked"):
            clicked_lat = map_data["last_object_clicked"]["lat"]
            clicked_lon = map_data["last_object_clicked"]["lng"]

            # Find the clicked substation
            clicked_substation = df[
                (df["latitude"] == clicked_lat) & (df["longitude"] == clicked_lon)
            ]

            if not clicked_substation.empty:
                substation_id = clicked_substation.iloc[0]["secondary_substation_id"]
                substation_name = clicked_substation.iloc[0][
                    "secondary_substation_name"
                ]

                st.write(f"**Selected Substation:** {substation_name}")
                st.write(f"**Substation ID:** {substation_id}")

                # Get all ESAs for this substation
                substation_esas = metadata_df[
                    metadata_df["secondary_substation_id"] == substation_id
                ]

                st.write(f"**Number of LV Feeders:** {len(substation_esas)}")

                # Date range selector
                col_date1, col_date2 = st.columns(2)
                with col_date1:
                    start_date = st.date_input(
                        "Start Date",
                        value=datetime.now() - timedelta(days=730),
                        max_value=datetime.now(),
                    )
                with col_date2:
                    end_date = st.date_input(
                        "End Date", value=datetime.now(), max_value=datetime.now()
                    )

                # Convert dates to datetime strings
                start_datetime = f"{start_date.strftime('%Y-%m-%d')}T00:00:00+00:00"
                end_datetime = f"{end_date.strftime('%Y-%m-%d')}T23:59:59+00:00"

                # Fetch smart meter data for all ESAs
                with st.spinner("Fetching smart meter data..."):
                    all_data = []
                    for _, esa_row in substation_esas.iterrows():
                        esa_id = esa_row["esa_id"]
                        lv_feeder_id = esa_row["lv_feeder_id"]

                        df_smart = fetch_smart_meter_data(
                            esa_id, start_datetime, end_datetime
                        )

                        if not df_smart.empty:
                            df_smart["lv_feeder_id"] = lv_feeder_id
                            all_data.append(df_smart)

                    if all_data:
                        combined_data = pd.concat(all_data, ignore_index=True)

                        # Convert timestamp to datetime
                        combined_data["data_timestamp"] = pd.to_datetime(
                            combined_data["data_timestamp"]
                        )

                        # Create the plot
                        fig = px.line(
                            combined_data,
                            x="data_timestamp",
                            y="active_total_consumption_import",
                            color="lv_feeder_id",
                            title=f"Smart Meter Values for Substation: {substation_name}",
                            labels={
                                "data_timestamp": "Timestamp",
                                "active_total_consumption_import": "Active Total Consumption Import (Wh)",
                                "lv_feeder_id": "LV Feeder ID",
                            },
                            height=500,
                        )

                        fig.update_layout(
                            xaxis_title="Timestamp",
                            yaxis_title="Active Total Consumption Import (Wh)",
                            legend_title="LV Feeder ID",
                            hovermode="x unified",
                        )

                        st.plotly_chart(fig, use_container_width=True)

                    else:
                        st.warning(
                            "No smart meter data available for this substation in the selected date range."
                        )
            else:
                st.info("Could not identify clicked substation.")
        else:
            st.info(
                "Click on a substation marker on the map to view its smart meter data."
            )

else:
    st.error("No data available. Please check the API connection.")
