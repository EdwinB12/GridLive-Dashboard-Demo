"""
Utility functions for GridLive API Dashboard
"""

import streamlit as st
import requests
import pandas as pd
import geopandas as gpd
from pyproj import Transformer
from datetime import datetime, timedelta
import time
from OSGridConverter import latlong2grid


# API Configuration
BASE_URL = "https://api.gridlive.shef.ac.uk"


@st.cache_data
def load_api_key():
    """Load API key from .streamlit/secrets.toml"""
    try:
        return st.secrets["GRIDLIVE_API_TOKEN"]
    except Exception as e:
        st.error(f"Error loading API key from secrets.toml: {str(e)}")
        return None


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


def fetch_smart_meter_data(api_key, esa_id, start_datetime=None, end_datetime=None):
    """
    Fetch smart meter data for a specific ESA

    Args:
        api_key: API key for authentication
        esa_id: The ESA ID to fetch data for
        start_datetime: Start datetime in ISO format (default: 30 days ago)
        end_datetime: End datetime in ISO format (default: now)

    Returns:
        DataFrame with smart meter data
    """
    if not api_key:
        st.error("API key not available")
        return pd.DataFrame()

    # Set default date range if not provided
    if not end_datetime:
        end_datetime = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+00:00")
    if not start_datetime:
        start_date = datetime.now() - timedelta(days=30)
        start_datetime = start_date.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    url = f"{BASE_URL}/smart_meter/esa/{esa_id}"
    headers = {"Authorization": api_key}
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


def convert_latlon_to_grid_reference(lat, lon):
    """
    Convert WGS84 latitude/longitude to UK Ordnance Survey Grid Reference

    Args:
        lat: Latitude in WGS84
        lon: Longitude in WGS84

    Returns:
        String: OS Grid Reference (e.g., "SU2792514662")
    """
    # Create transformer from WGS84 (EPSG:4326) to British National Grid (EPSG:27700)
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
    easting, northing = transformer.transform(lon, lat)

    # The origin of the British National Grid is 400km west and 100km north of the true origin
    # to avoid negative numbers. The grid starts at grid square SV (Scilly Isles)

    # Calculate position in the 500km grid
    e_500 = int(easting / 500000)
    n_500 = int(northing / 500000)

    # Calculate position in the 100km grid within the 500km square
    e_100 = int((easting % 500000) / 100000)
    n_100 = int((northing % 500000) / 100000)

    # First letter: 500km grid
    # Grid layout for 500km squares (2x2 covering UK):
    # N O
    # H J
    # S T (with S being southwest)
    first_letters = [
        ["S", "T"],  # Row 0 (south): 0-500km north
        ["N", "O"],  # Row 1 (north): 500-1000km north
        ["H", "J"],  # Row 2 (far north): 1000-1500km north
    ]

    # Select first letter
    if n_500 < len(first_letters) and e_500 < len(first_letters[n_500]):
        first_letter = first_letters[n_500][e_500]
    else:
        # Fallback for out of range
        first_letter = "S"

    # Second letter: 100km grid within the 500km square
    # The actual UK OS grid uses this specific layout for 100km squares:
    # Each 500km square is divided into a 5x5 grid of 100km squares
    #
    # The letters run A-Z (excluding I) in columns from west to east,
    # with the northing index counting from the TOP (north) down
    #
    # For the S square (SW England), this creates:
    #   Row 0 (400-500km N): SV SW SX SY SZ  (northing index 0 = top)
    #   Row 1 (300-400km N): SQ SR SS ST SU
    #   Row 2 (200-300km N): SL SM SN SO SP
    #   Row 3 (100-200km N): SF SG SH SJ SK
    #   Row 4 (0-100km N):   SA SB SC SD SE  (northing index 4 = bottom)
    #
    # So the array is [easting_index][reversed_northing_index]

    # Define as [easting_index][northing_index_from_top] for direct lookup
    second_letters = [
        ["V", "Q", "L", "F", "A"],  # Column 0 (0-100km E), from north to south
        ["W", "R", "M", "G", "B"],  # Column 1 (100-200km E)
        ["X", "S", "N", "H", "C"],  # Column 2 (200-300km E)
        ["Y", "T", "O", "J", "D"],  # Column 3 (300-400km E)
        ["Z", "U", "P", "K", "E"],  # Column 4 (400-500km E)
    ]

    # Reverse the northing index (count from top instead of bottom)
    n_100_reversed = 4 - n_100
    second_letter = second_letters[e_100][n_100_reversed]

    # Get the numeric part (within the 100km square)
    e_within = int(easting % 100000)
    n_within = int(northing % 100000)

    # Return as a 10-digit grid reference (1m precision)
    grid_ref = f"{first_letter}{second_letter}{e_within:05d}{n_within:05d}"

    return grid_ref


@st.cache_data(ttl=3600)
def fetch_esa_metadata_near(grid_reference, radius=10000, limit=None):
    """
    Fetch ESA metadata near a grid reference

    Args:
        grid_reference: OS Grid Reference (e.g., "SK387865")
        radius: Radius in meters (default: 10000, max: 100000)
        limit: Number of records to fetch (None for all)

    Returns:
        DataFrame with ESA metadata
    """
    url = f"{BASE_URL}/esa_metadata/near/{grid_reference}"

    params = {"radius": radius}
    if limit:
        params["limit"] = limit

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if data:
            return pd.DataFrame(data)
        else:
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Error fetching data near {grid_reference}: {str(e)}")
        return pd.DataFrame()


def process_esa_metadata(metadata_df: pd.DataFrame) -> pd.DataFrame:
    # Groupby secondary_substation_id and get number of rows
    metadata_df["number_of_feeders"] = metadata_df.groupby("secondary_substation_id")[
        "secondary_substation_id"
    ].transform("count")

    # Create display dataframe with unique substations
    locations_df = metadata_df.drop_duplicates(subset=["secondary_substation_id"])

    # Use geopandas for efficient coordinate conversion from EPSG:27700 to EPSG:4326
    gdf = gpd.GeoDataFrame(
        locations_df,
        geometry=gpd.points_from_xy(
            locations_df["esa_location_eastings"],
            locations_df["esa_location_northings"],
        ),
        crs="EPSG:27700",
    )
    gdf = gdf.to_crs("EPSG:4326")
    locations_df["longitude"] = gdf.geometry.x
    locations_df["latitude"] = gdf.geometry.y

    return locations_df


def latlon_to_grid_reference(lat: float, lon: float) -> str:
    """
    Convert latitude/longitude to British National Grid reference.

    Args:
        lat: Latitude (WGS84)
        lon: Longitude (WGS84)

    Returns:
        Grid reference string (e.g., "SK356745")
    """
    grid = latlong2grid(lat, lon)
    # Remove spaces from string
    grid = str(grid).replace(" ", "")
    return grid


@st.cache_data(ttl=3600)
def fetch_esa_metadata_near_grid(grid_reference: str, radius: int = 5000):
    """
    Fetch ESA metadata near a grid reference within a radius.

    Args:
        grid_reference: British National Grid reference (e.g., "SK356745")
        radius: Radius in meters (default: 5000m = 5km)

    Returns:
        DataFrame with ESA metadata
    """
    url = f"{BASE_URL}/esa_metadata/near/{grid_reference}"
    params = {"radius": radius}

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if data:
            return pd.DataFrame(data)
        else:
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Error fetching data near {grid_reference}: {str(e)}")
        return pd.DataFrame()
