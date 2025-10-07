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


def get_color_for_feeders(
    num_feeders: int, min_feeders: int, max_feeders: int
) -> str:
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
    colormap = cm.get_cmap("RdYlGn_r")
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
            color = get_color_for_feeders(
                row.number_of_feeders, min_feeders, max_feeders
            )

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
    combined_data: pd.DataFrame,
    substation_name: str,
    y_column: str = "active_total_consumption_import",
) -> px.line:
    """
    Create a plotly line plot for smart meter data.

    Args:
        combined_data: DataFrame with smart meter data
        substation_name: Name of the substation for the title
        y_column: Column name to plot on y-axis (default: "active_total_consumption_import")

    Returns:
        plotly.graph_objects.Figure
    """
    # Remove any values over 10 million (likely data errors)
    combined_data = combined_data[combined_data[y_column] <= 10_000_000].copy()

    # Sort data by timestamp
    combined_data = combined_data.sort_values(by="data_timestamp")

    # Create readable label from column name
    y_label = y_column.replace("_", " ").title()

    # Add "Wh" unit if column ends with "import"
    if y_column.endswith("import"):
        y_label += " (Wh)"

    # Calculate max value for active_total_consumption_import
    max_value = None
    title = f"Smart Meter Values for Substation: {substation_name}"
    if y_column == "active_total_consumption_import":
        max_value = combined_data[y_column].max()
        title += f"<br><sub>Maximum Consumption: {max_value:.2f} Wh</sub>"

    fig = px.line(
        combined_data,
        x="data_timestamp",
        y=y_column,
        color="lv_feeder_id",
        title=title,
        labels={
            "data_timestamp": "Timestamp",
            y_column: y_label,
            "lv_feeder_id": "LV Feeder ID",
        },
        height=500,
    )

    # Add horizontal dashed red line at max value for active_total_consumption_import
    if y_column == "active_total_consumption_import" and max_value is not None:
        fig.add_hline(
            y=max_value,
            line_dash="dash",
            line_color="red",
            annotation_text=f"Max: {max_value:.2f} Wh",
            annotation_position="top",
        )

    fig.update_layout(
        xaxis_title="Timestamp",
        yaxis_title=y_label,
        legend_title="LV Feeder ID",
        hovermode="x unified",
    )

    return fig
