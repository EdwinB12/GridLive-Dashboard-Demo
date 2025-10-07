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

    start = time.time()

    if license_areas and len(license_areas) > 0:
        # Fetch data for each selected license area
        for license_area in license_areas:
            print(f"Fetching data for license area: {license_area}")
            url = f"{BASE_URL}/esa_metadata/license_area/{license_area}"

            params = {}
            if limit:
                params["limit"] = limit

            try:
                start_of_api_call = time.time()
                response = requests.get(url, params=params)
                end_of_api_call = time.time()
                print(
                    f"API call duration for {license_area}: {end_of_api_call - start_of_api_call:.2f} seconds"
                )
                response.raise_for_status()
                data = response.json()
                all_data.extend(data)
            except Exception as e:
                st.error(f"Error fetching data for {license_area}: {str(e)}")

        if all_data:
            end = time.time()
            st.success(
                f"Fetched {len(all_data)} records in {end - start:.2f} seconds"
            )
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
