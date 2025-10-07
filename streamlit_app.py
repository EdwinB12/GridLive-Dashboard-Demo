import streamlit as st
import pandas as pd
from streamlit_folium import st_folium
from datetime import datetime, timedelta

# Import utility functions
from utils import (
    load_api_key,
    fetch_license_areas,
    fetch_esa_metadata,
    fetch_smart_meter_data,
    process_esa_metadata,
)

# Import plotting functions
from plotting import create_substation_map, create_smart_meter_plot

# Page configuration
st.set_page_config(page_title="GridLive API Dashboard", page_icon="⚡", layout="wide")

# Title
st.title("⚡ GridLive API Dashboard")

# Sidebar controls
st.sidebar.header("Settings")

# Load API key
API_KEY = load_api_key()

# Fetch available license areas
AVAILABLE_LICENSE_AREAS = fetch_license_areas()

# Desigining Button on sidebar
if AVAILABLE_LICENSE_AREAS:
    # License area multi-select with "All" option
    license_area_options = ["All"] + AVAILABLE_LICENSE_AREAS
    selected_license_area = st.sidebar.selectbox(
        "Select License Area",
        options=license_area_options,
        index=0,
        help="Select a license area to filter substations. Select 'All' to show all areas.",
    )

    # Convert selection to list format for backwards compatibility
    if selected_license_area == "All":
        selected_license_areas = AVAILABLE_LICENSE_AREAS
    else:
        selected_license_areas = [selected_license_area]
else:
    selected_license_areas = None
    st.sidebar.warning("Could not load license areas")

# Number of ESAs per license area limit
data_limit = st.sidebar.number_input(
    "ESAs per license area",
    min_value=0,
    max_value=10000,
    value=5,
    step=100,
    help="Number of ESAs to load per selected license area (0 for unlimited). Higher values may take longer to load.",
)

# Convert 0 to None for unlimited
limit_value = None if data_limit == 0 else data_limit

# Fetch data
with st.spinner("Fetching metadata from GridLive API..."):
    metadata_df = fetch_esa_metadata(
        limit=limit_value,
        license_areas=selected_license_areas,
    )

if not metadata_df.empty:
    # Calculate statistics
    num_unique_substations = metadata_df["secondary_substation_id"].nunique()
    num_esas = len(metadata_df)

    # Show selected license area info
    if len(selected_license_areas) > 1:
        st.sidebar.info("**Showing all license areas**")
    else:
        st.sidebar.info(f"**Selected area:** {selected_license_areas[0]}")

    # Convert coordinates
    with st.spinner("Converting coordinates..."):
        locations_df = process_esa_metadata(metadata_df)

    st.sidebar.success(f"Loaded {len(locations_df)} substations")

    # Create two-column layout
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("UK Substation Locations")
        st.write("Click on a substation to view smart meter data")

        # Create map with color coding based on selection
        show_all_areas = len(selected_license_areas) > 1
        m = create_substation_map(locations_df, show_all_areas=show_all_areas)

        # Display map and capture click data
        map_data = st_folium(m, width=700, height=600)

    with col2:
        st.subheader("Smart Meter Data")

        # Initialize session state for tracking clicks and caching data
        if "last_clicked_substation" not in st.session_state:
            st.session_state.last_clicked_substation = None
        if "last_date_range" not in st.session_state:
            st.session_state.last_date_range = None
        if "cached_smart_meter_data" not in st.session_state:
            st.session_state.cached_smart_meter_data = None

        # Check if a marker was clicked
        if map_data and map_data.get("last_object_clicked"):
            clicked_lat = map_data["last_object_clicked"]["lat"]
            clicked_lon = map_data["last_object_clicked"]["lng"]

            # Find the clicked substation
            clicked_substation = locations_df[
                (locations_df["latitude"] == clicked_lat)
                & (locations_df["longitude"] == clicked_lon)
            ]

            if not clicked_substation.empty:
                substation_id = clicked_substation.iloc[0]["secondary_substation_id"]
                substation_name = clicked_substation.iloc[0][
                    "secondary_substation_name"
                ]

                # Get all ESAs for this substation
                substation_esas = metadata_df[
                    metadata_df["secondary_substation_id"] == substation_id
                ]

                st.write(f"**Selected Substation:** {substation_name} | **Substation ID:** {substation_id} | **Number of LV Feeders:** {len(substation_esas)}")

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
                current_date_range = (start_datetime, end_datetime)

                # Check if we need to fetch new data
                need_to_fetch = (
                    st.session_state.last_clicked_substation != substation_id
                    or st.session_state.last_date_range != current_date_range
                )

                if need_to_fetch:
                    # Fetch smart meter data for all ESAs
                    with st.spinner(
                        "Fetching smart meter data (max 10 lv feeders)..."
                    ):
                        all_data = []
                        count = 0
                        for _, esa_row in substation_esas.iterrows():
                            esa_id = esa_row["esa_id"]
                            lv_feeder_id = esa_row["lv_feeder_id"]

                            df_smart = fetch_smart_meter_data(
                                API_KEY, esa_id, start_datetime, end_datetime
                            )

                            if not df_smart.empty:
                                df_smart["lv_feeder_id"] = lv_feeder_id
                                all_data.append(df_smart)
                            count += 1
                            if count >= 10:  # Limit to 10 feeders
                                break

                        # Cache the result
                        st.session_state.last_clicked_substation = substation_id
                        st.session_state.last_date_range = current_date_range
                        st.session_state.cached_smart_meter_data = (
                            all_data,
                            substation_name,
                        )

                # Use cached data
                if st.session_state.cached_smart_meter_data:
                    all_data, cached_substation_name = (
                        st.session_state.cached_smart_meter_data
                    )

                    if all_data:
                        combined_data = pd.concat(all_data, ignore_index=True)

                        # Convert timestamp to datetime
                        combined_data["data_timestamp"] = pd.to_datetime(
                            combined_data["data_timestamp"]
                        )

                        # Get available columns for plotting (exclude esa_id and data_timestamp)
                        exclude_columns = ["esa_id", "data_timestamp", "lv_feeder_id"]
                        available_columns = [
                            col
                            for col in combined_data.columns
                            if col not in exclude_columns
                        ]

                        # Column selector dropdown
                        if available_columns:
                            default_column = (
                                "active_total_consumption_import"
                                if "active_total_consumption_import"
                                in available_columns
                                else available_columns[0]
                            )
                            selected_column = st.selectbox(
                                "Select data to plot:",
                                options=available_columns,
                                index=available_columns.index(default_column),
                            )

                            # Create and display the plot
                            fig = create_smart_meter_plot(
                                combined_data, cached_substation_name, selected_column
                            )
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.warning("No plottable columns available in the data.")

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
