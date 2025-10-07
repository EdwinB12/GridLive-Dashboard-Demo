"""
Plotting functions for GridLive API Dashboard
"""

import folium
import pandas as pd
import plotly.express as px
import matplotlib.colors as mcolors
import matplotlib.cm as cm


def get_color_for_license_area(license_area: str, color_map: dict) -> str:
    """
    Get a consistent color for a license area from a color map.

    Args:
        license_area: Name of the license area
        color_map: Dictionary mapping license area names to colors

    Returns:
        Color string for the license area
    """
    return color_map.get(license_area, "gray")


def get_color_for_feeders(num_feeders: int, min_feeders: int, max_feeders: int) -> str:
    """
    Get a color based on the number of feeders using a continuous color scale.

    Args:
        num_feeders: Number of feeders at the substation
        min_feeders: Minimum number of feeders in the dataset
        max_feeders: Maximum number of feeders in the dataset

    Returns:
        Hex color string based on feeder count
    """
    # Avoid division by zero
    if max_feeders == min_feeders:
        return "#3388ff"  # Default blue color

    # Normalize to 0-1 range
    normalized = (num_feeders - min_feeders) / (max_feeders - min_feeders)

    # Use RdYlGn_r colormap (green for low, yellow for mid, red for high)
    colormap = cm.get_cmap('RdYlGn_r')
    rgba = colormap(normalized)

    # Convert to hex color
    hex_color = mcolors.rgb2hex(rgba)
    return hex_color


def create_substation_map(
    locations_df: pd.DataFrame, show_all_areas: bool = False
) -> folium.Map:
    """
    Create a folium map with substation markers.

    Args:
        locations_df: DataFrame with substation locations and metadata
        show_all_areas: If True, color by license area. If False, color by number of feeders.

    Returns:
        folium.Map object with markers
    """
    # Create map centered on UK
    m = folium.Map(
        location=[54.5, -2.0],  # Center of UK
        zoom_start=6,
        tiles="OpenStreetMap",
    )

    # Create color map for license areas if showing all areas
    if show_all_areas:
        unique_areas = locations_df["license_area_name"].unique()
        # Use a color palette for different license areas
        colors = [
            "blue",
            "red",
            "green",
            "purple",
            "orange",
            "darkred",
            "lightred",
            "beige",
            "darkblue",
            "darkgreen",
            "cadetblue",
            "darkpurple",
            "pink",
            "lightblue",
            "lightgreen",
            "gray",
            "black",
            "lightgray",
        ]
        color_map = {
            area: colors[i % len(colors)] for i, area in enumerate(unique_areas)
        }
    else:
        # Calculate min/max feeders for continuous color scale
        min_feeders = locations_df["number_of_feeders"].min()
        max_feeders = locations_df["number_of_feeders"].max()

    # Add markers efficiently using itertuples (faster than iterrows)
    for row in locations_df.itertuples():
        # Determine color based on mode
        if show_all_areas:
            color = get_color_for_license_area(row.license_area_name, color_map)
        else:
            color = get_color_for_feeders(row.number_of_feeders, min_feeders, max_feeders)

        folium.CircleMarker(
            location=[row.latitude, row.longitude],
            radius=4,
            popup=folium.Popup(
                f"""<b>{row.secondary_substation_name}</b><br>
                Secondary Substation ID: {row.secondary_substation_id}<br>
                DNO: {row.dno_name}<br>
                License Area: {row.license_area_name}<br>
                Number of Feeders: {row.number_of_feeders}""",
                max_width=300,
            ),
            tooltip=row.secondary_substation_name,
            color=color,
            fill=True,
            fillOpacity=0.7,
        ).add_to(m)

    return m


def create_smart_meter_plot(
    combined_data: pd.DataFrame, substation_name: str
) -> px.line:
    """
    Create a plotly line plot for smart meter data.

    Args:
        combined_data: DataFrame with smart meter data
        substation_name: Name of the substation for the title

    Returns:
        plotly.graph_objects.Figure
    """
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

    return fig
