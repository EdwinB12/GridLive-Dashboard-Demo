import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from datetime import datetime, timedelta

# Import utility functions
from utils import (
    load_api_key,
    fetch_license_areas,
    fetch_esa_metadata,
    fetch_esa_metadata_near_grid,
    fetch_smart_meter_data,
    process_esa_metadata,
    latlon_to_grid_reference,
    calculate_substation_aggregate,
    smooth_timeseries,
    TOTAL_SECONDARY_CUSTOMERS,
)

# Import plotting functions
from plotting import create_substation_map, create_smart_meter_plot, create_map_with_radius_circle, create_substation_aggregate_plot

# Page configuration
st.set_page_config(page_title="GridLive API Dashboard", page_icon="⚡", layout="wide")

# Remove top padding
st.markdown("""
    <style>
        .block-container {
            padding-top: 1rem;
        }
    </style>
    """, unsafe_allow_html=True)

# Title
col_title, col_links = st.columns([3, 1])
with col_title:
    st.title("⚡ GridLive API Dashboard")
with col_links:
    st.markdown(
        """
        <div style="margin-top: 35px; text-align: right;">
            <a href="https://sites.google.com/sheffield.ac.uk/gridlive/home?authuser=0" target="_blank" style="margin-right: 15px; text-decoration: none;">
                🌐 GridLive Website
            </a>
            <a href="https://api.gridlive.shef.ac.uk/docs#" target="_blank" style="text-decoration: none;">
                📚 API Docs
            </a>
        </div>
        """,
        unsafe_allow_html=True
    )

st.markdown(
    """
    <div>
        <span style="background-color: #ff4b4b; color: white; padding: 5px 10px; border-radius: 5px; font-size: 14px; font-weight: bold;">
            ALPHA VERSION
        </span>
        <span style="margin-left: 10px; font-size: 14px;">
            This app is currently experimental. Expect it to change without warning and things not to work.
            Please feel free to email me at <a href="mailto:w.e.brown@sheffield.ac.uk">w.e.brown@sheffield.ac.uk</a> with any feedback or questions.
        </span>
    </div>
    """,
    unsafe_allow_html=True
)

# Sidebar controls
st.sidebar.header("Settings")

# Load API key
API_KEY = load_api_key()

# Mode selection
mode = st.sidebar.radio(
    "Selection Mode",
    options=["Map Click", "License Area"],
    index=0,
    help="Choose how to select substations: by clicking on the map or by License Area",
)

# Fetch available license areas
AVAILABLE_LICENSE_AREAS = fetch_license_areas()

# Mode-specific controls
if mode == "License Area":
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

    # Number of substations per license area limit
    data_limit = st.sidebar.number_input(
        "Substations per license area",
        min_value=0,
        max_value=10000,
        value=5,
        step=100,
        help="Number of substations to load per selected license area (0 for unlimited). Higher values may take longer to load.",
    )

    # Warning for high limits with "All" selected
    if selected_license_area == "All" and data_limit > 100:
        st.sidebar.warning(
            "⚠️ **Performance Warning**\n\n"
            f"Loading {data_limit} substations per license area with 'All' selected may cause the app to struggle.\n\n"
            "**Recommendation:** Either:\n"
            "- Reduce substations per area to ≤100, or\n"
            "- Select a specific license area"
        )

    # Convert 0 to None for unlimited
    limit_value = None if data_limit == 0 else data_limit
else:
    # Map Click mode
    selected_license_areas = None
    limit_value = None

    # Radius selection
    radius = st.sidebar.number_input(
        "Search Radius (meters)",
        min_value=0,
        max_value=100000,
        value=5000,
        step=1000,
        help="Radius in meters to search around the clicked point (max 100,000m)",
    )

    st.sidebar.info(
        "Click on the map to select a location and load nearby substations"
    )

# Initialize session state for map click mode
if "map_click_location" not in st.session_state:
    st.session_state.map_click_location = None
if "map_click_grid_ref" not in st.session_state:
    st.session_state.map_click_grid_ref = None
if "view_mode" not in st.session_state:
    st.session_state.view_mode = "Substation Aggregate"

# Fetch data based on mode
metadata_df = pd.DataFrame()

if mode == "License Area":
    # Fetch data using license area
    with st.spinner("Fetching metadata from GridLive API..."):
        metadata_df = fetch_esa_metadata(
            limit=limit_value,
            license_areas=selected_license_areas,
        )
else:
    # Map Click mode - only fetch if a location has been clicked
    if st.session_state.map_click_location is not None:
        grid_ref = st.session_state.map_click_grid_ref
        with st.spinner(
            f"Fetching substations near {grid_ref} within {radius}m radius..."
        ):
            metadata_df = fetch_esa_metadata_near_grid(
                grid_reference=grid_ref,
                radius=radius,
            )

# Create two-column layout
col1, col2 = st.columns([1, 1])

# Variable to hold locations data
locations_df = pd.DataFrame()
map_data = None

with col1:
    st.subheader("UK Substation Locations")

    if mode == "License Area":
        st.write("Choose a license area and a number of substations to show.")
    else:
        st.write(
            "Click on the map to select all substations within a circle with a set radius (left handside)"
        )

    # Create initial map if in Map Click mode or if data is available
    if mode == "Map Click":
        # Show empty map for clicking or map with substations
        if st.session_state.map_click_location is not None:
            # User has clicked - show map with radius circle centered on click
            click_lat, click_lon = st.session_state.map_click_location

            if not metadata_df.empty:
                # Show map with loaded substations
                locations_df = process_esa_metadata(metadata_df)
                st.sidebar.success(f"Loaded {len(locations_df)} substations")
                m = create_map_with_radius_circle(
                    click_lat, click_lon, radius, locations_df
                )
            else:
                # Show map with just the click location and radius circle
                m = create_map_with_radius_circle(
                    click_lat, click_lon, radius, None
                )
        else:
            # No click yet - show empty UK map
            st.info("Please click on the map to select a location")
            m = folium.Map(
                location=[54.5, -2.0],  # Center of UK
                zoom_start=6,
                tiles="OpenStreetMap",
            )

        # Display map and capture click data
        map_data = st_folium(m, width=700, height=600, key="map_click_mode")

        # Display click information
        if st.session_state.map_click_location is not None:
            click_lat, click_lon = st.session_state.map_click_location
            st.write("**Click Location:**")
            st.write(f"Latitude: {click_lat:.6f}, Longitude: {click_lon:.6f}")
            st.write(f"Grid Reference: {st.session_state.map_click_grid_ref}")
            st.write(f"Search Radius: {radius} meters")

        # Handle map clicks in Map Click mode
        if map_data and map_data.get("last_clicked"):
            clicked_lat = map_data["last_clicked"]["lat"]
            clicked_lon = map_data["last_clicked"]["lng"]

            # Check if this is a new click (not a substation marker)
            is_new_location = (
                st.session_state.map_click_location is None
                or abs(clicked_lat - st.session_state.map_click_location[0]) > 0.001
                or abs(clicked_lon - st.session_state.map_click_location[1]) > 0.001
            )

            if is_new_location:
                # Convert to grid reference
                grid_ref = latlon_to_grid_reference(clicked_lat, clicked_lon)
                st.session_state.map_click_location = (clicked_lat, clicked_lon)
                st.session_state.map_click_grid_ref = grid_ref
                st.rerun()

    elif not metadata_df.empty:
        # License Area mode with data
        # Show selected license area info
        if selected_license_areas and len(selected_license_areas) > 1:
            st.sidebar.info("**Showing all license areas**")
        elif selected_license_areas:
            st.sidebar.info(f"**Selected area:** {selected_license_areas[0]}")

        # Convert coordinates
        with st.spinner("Converting coordinates..."):
            locations_df = process_esa_metadata(metadata_df)

        st.sidebar.success(f"Loaded {len(locations_df)} substations")

        # Create map with color coding based on selection
        show_all_areas = selected_license_areas and len(selected_license_areas) > 1
        m = create_substation_map(locations_df, show_all_areas=show_all_areas)

        # Display map and capture click data
        map_data = st_folium(m, width=700, height=600)

# Smart meter data section
if not metadata_df.empty and not locations_df.empty:
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
                sub = clicked_substation.iloc[0]
                substation_id = sub["secondary_substation_id"]
                substation_name = sub["secondary_substation_name"]
                substation_key = sub["substation_key"]

                # Get all ESAs for this substation, using name for SSEN (id not unique)
                if sub["dno_name"] == "SSEN":
                    substation_esas = metadata_df[
                        metadata_df["secondary_substation_name"] == substation_name
                    ]
                else:
                    substation_esas = metadata_df[
                        metadata_df["secondary_substation_id"] == substation_id
                    ]
                easting = sub["esa_location_eastings"]
                northing = sub["esa_location_northings"]
                lat = sub["latitude"]
                lon = sub["longitude"]

                col_info, col_meta_dl = st.columns([3, 1])
                with col_info:
                    st.write(
                        f"**Selected Substation:** {substation_name} | **Substation ID:** {substation_id} | **Number of LV Feeders:** {len(substation_esas)}"
                    )
                    st.write(
                        f"**Location (BNG):** E {easting:,.0f}, N {northing:,.0f} | "
                        f"**Location (WGS84):** {lat:.6f}°N, {lon:.6f}°E"
                    )
                with col_meta_dl:
                    st.download_button(
                        label="Download Metadata",
                        data=substation_esas.to_csv(index=False),
                        file_name=f"{substation_name}_metadata.csv",
                        mime="text/csv",
                    )

                # View mode toggle
                view_options = ["Substation Aggregate", "Modelled", "Individual Feeders"]
                view_mode = st.radio(
                    "View",
                    options=view_options,
                    index=view_options.index(st.session_state.view_mode) if st.session_state.view_mode in view_options else 0,
                    horizontal=True,
                )
                st.session_state.view_mode = view_mode

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
                    st.session_state.last_clicked_substation != substation_key
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
                        st.session_state.last_clicked_substation = substation_key
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

                        # Get available columns for plotting (exclude metadata columns)
                        exclude_columns = ["esa_id", "data_timestamp", "lv_feeder_id"]
                        available_columns = [
                            col
                            for col in combined_data.columns
                            if col not in exclude_columns
                        ]

                        if not available_columns:
                            st.warning("No plottable columns available in the data.")
                        elif view_mode == "Substation Aggregate":
                            default_column = (
                                "active_total_consumption_import"
                                if "active_total_consumption_import" in available_columns
                                else available_columns[0]
                            )
                            selected_column = st.selectbox(
                                "Select data to plot:",
                                options=available_columns,
                                index=available_columns.index(default_column),
                            )

                            aggregate_data = calculate_substation_aggregate(
                                all_data, selected_column, TOTAL_SECONDARY_CUSTOMERS
                            )

                            if aggregate_data.empty:
                                st.warning(
                                    "Could not compute aggregate — `active_device_count` "
                                    "not available in smart meter data."
                                )
                            else:
                                aggregate_data["data_timestamp"] = pd.to_datetime(
                                    aggregate_data["data_timestamp"]
                                )
                                fig = create_substation_aggregate_plot(
                                    aggregate_data,
                                    cached_substation_name,
                                    selected_column,
                                    TOTAL_SECONDARY_CUSTOMERS,
                                )
                                st.plotly_chart(fig, use_container_width=True)
                                st.download_button(
                                    label="Download CSV",
                                    data=aggregate_data.to_csv(index=False),
                                    file_name=f"{cached_substation_name}_aggregate_{selected_column}.csv",
                                    mime="text/csv",
                                )
                        elif view_mode == "Modelled":
                            default_column = (
                                "active_total_consumption_import"
                                if "active_total_consumption_import" in available_columns
                                else available_columns[0]
                            )
                            selected_column = st.selectbox(
                                "Select data to plot:",
                                options=available_columns,
                                index=available_columns.index(default_column),
                            )

                            aggregate_data = calculate_substation_aggregate(
                                all_data, selected_column, TOTAL_SECONDARY_CUSTOMERS
                            )

                            if aggregate_data.empty:
                                st.warning(
                                    "Could not compute aggregate — `active_device_count` "
                                    "not available in smart meter data."
                                )
                            else:
                                aggregate_data["data_timestamp"] = pd.to_datetime(
                                    aggregate_data["data_timestamp"]
                                )
                                modelled_data = smooth_timeseries(aggregate_data, selected_column)
                                fig = create_substation_aggregate_plot(
                                    modelled_data,
                                    cached_substation_name,
                                    selected_column,
                                    TOTAL_SECONDARY_CUSTOMERS,
                                    label="Modelled Substation Demand",
                                )
                                st.plotly_chart(fig, use_container_width=True)
                                st.download_button(
                                    label="Download CSV",
                                    data=modelled_data.to_csv(index=False),
                                    file_name=f"{cached_substation_name}_modelled_{selected_column}.csv",
                                    mime="text/csv",
                                )
                        else:
                            # Individual feeders view
                            default_column = (
                                "active_total_consumption_import"
                                if "active_total_consumption_import" in available_columns
                                else available_columns[0]
                            )
                            selected_column = st.selectbox(
                                "Select data to plot:",
                                options=available_columns,
                                index=available_columns.index(default_column),
                            )

                            fig = create_smart_meter_plot(
                                combined_data, cached_substation_name, selected_column
                            )
                            st.plotly_chart(fig, use_container_width=True)
                            st.download_button(
                                label="Download CSV",
                                data=combined_data.to_csv(index=False),
                                file_name=f"{cached_substation_name}_feeders_{selected_column}.csv",
                                mime="text/csv",
                            )

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
elif mode == "License Area":
    with col2:
        st.error("No data available. Please check the API connection.")
