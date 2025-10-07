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
    locations_df: pd.DataFrame,
    show_all_areas: bool = False,
    center: list = None,
    zoom: int = None,
) -> folium.Map:
    """
    Create a folium map with substation markers.

    Args:
        locations_df: DataFrame with substation locations and metadata
        show_all_areas: If True, color by license area. If False, color by number of feeders.
        center: Map center as [lat, lon]. Defaults to UK center.
        zoom: Map zoom level. Defaults to 6.

    Returns:
        folium.Map object with markers
    """
    # Create map with specified or default center and zoom
    if center is None:
        center = [54.5, -2.0]  # Center of UK
    if zoom is None:
        zoom = 6

    m = folium.Map(
        location=center,
        zoom_start=zoom,
        tiles="OpenStreetMap",
    )

    # If empty dataframe, just return the map
    if locations_df.empty:
        return m

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

    # Add legend/colorbar
    if show_all_areas:
        # Create HTML legend for license areas
        legend_html = """
        <div style="position: fixed;
                    bottom: 50px; left: 50px; width: 150px;
                    background-color: white; z-index:9999; font-size:11px;
                    border:1px solid grey; border-radius: 3px; padding: 6px">
        <p style="margin: 0 0 6px 0; font-weight: bold;">License Areas</p>
        """
        for area, color in sorted(color_map.items()):
            legend_html += f"""
            <p style="margin: 3px 0;">
                <i style="background:{color}; width: 12px; height: 12px;
                   display: inline-block; border: 1px solid #000; opacity: 0.7;"></i>
                {area}
            </p>
            """
        legend_html += "</div>"
        m.get_root().html.add_child(folium.Element(legend_html))
    else:
        # Create colorbar for continuous feeder scale
        colorbar_html = f"""
        <div style="position: fixed;
                    bottom: 50px; left: 50px; width: 150px;
                    background-color: white; z-index:9999; font-size:11px;
                    border:1px solid grey; border-radius: 3px; padding: 6px">
        <p style="margin: 0 0 6px 0; font-weight: bold;">Number of Feeders</p>
        <div style="background: linear-gradient(to right,
                    rgb(0,104,55), rgb(166,217,106), rgb(255,255,191),
                    rgb(253,174,97), rgb(165,0,38));
                    height: 15px; width: 100%; border: 1px solid #000;"></div>
        <div style="display: flex; justify-content: space-between; margin-top: 3px;">
            <span>{int(min_feeders)}</span>
            <span>{int(max_feeders)}</span>
        </div>
        </div>
        """
        m.get_root().html.add_child(folium.Element(colorbar_html))

    return m


def calculate_zoom_level(radius: int, map_height: int = 600) -> int:
    """
    Calculate appropriate zoom level to fit a circle of given radius in the map view.

    Args:
        radius: Radius in meters
        map_height: Map height in pixels (default 600)

    Returns:
        Appropriate zoom level (1-18)
    """
    # At zoom level z, the map shows approximately:
    # meters_per_pixel = 156543.03392 * cos(latitude) / (2 ^ z)
    # For UK (latitude ~54°), we need the circle diameter to fit in the view
    # Assuming we want the circle to take up about 70% of the smaller dimension

    # Approximate meters per pixel at different zoom levels (at UK latitude ~54°)
    # Using the Web Mercator projection formula
    import math

    lat_radians = math.radians(54.0)  # UK approximate latitude

    # We want diameter (2 * radius) to fit in about 70% of the view
    target_meters = radius * 2 / 0.7

    # Calculate zoom level
    # meters_per_pixel = 156543.03392 * cos(lat) / (2^zoom)
    # Available pixels ≈ map_height (using height as it's typically the limiting dimension)
    meters_per_pixel = target_meters / map_height

    # Solve for zoom: 2^zoom = 156543.03392 * cos(lat) / meters_per_pixel
    zoom = math.log2(156543.03392 * math.cos(lat_radians) / meters_per_pixel)

    # Clamp zoom level to valid range (1-18)
    zoom_level = int(max(1, min(18, zoom)))

    return zoom_level


def create_map_with_radius_circle(
    center_lat: float, center_lon: float, radius: int, locations_df: pd.DataFrame = None
) -> folium.Map:
    """
    Create a map centered on a location with a radius circle and optional substation markers.
    The zoom level is automatically calculated to fit the circle in the view.

    Args:
        center_lat: Center latitude
        center_lon: Center longitude
        radius: Radius in meters
        locations_df: Optional DataFrame with substation locations

    Returns:
        folium.Map object
    """
    # Calculate optimal zoom level based on radius
    zoom_level = calculate_zoom_level(radius)

    # Create map centered on the clicked location
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom_level,
        tiles="OpenStreetMap",
    )

    # Add a circle to show the search radius
    folium.Circle(
        location=[center_lat, center_lon],
        radius=radius,
        color="blue",
        fill=True,
        fillColor="blue",
        fillOpacity=0.1,
        popup=f"Search radius: {radius}m",
        tooltip=f"Search area ({radius}m radius)",
    ).add_to(m)

    # Add a marker for the clicked location
    folium.Marker(
        location=[center_lat, center_lon],
        popup="Selected Location",
        tooltip="Clicked Location",
        icon=folium.Icon(color="red", icon="info-sign"),
    ).add_to(m)

    # Add substation markers if data is available
    if locations_df is not None and not locations_df.empty:
        # Calculate min/max feeders for continuous color scale
        min_feeders = locations_df["number_of_feeders"].min()
        max_feeders = locations_df["number_of_feeders"].max()

        # Add markers for substations
        for row in locations_df.itertuples():
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

        # Add colorbar for feeders
        colorbar_html = f'''
        <div style="position: fixed;
                    bottom: 50px; left: 50px; width: 150px;
                    background-color: white; z-index:9999; font-size:11px;
                    border:1px solid grey; border-radius: 3px; padding: 6px">
        <p style="margin: 0 0 6px 0; font-weight: bold;">Number of Feeders</p>
        <div style="background: linear-gradient(to right,
                    rgb(0,104,55), rgb(166,217,106), rgb(255,255,191),
                    rgb(253,174,97), rgb(165,0,38));
                    height: 15px; width: 100%; border: 1px solid #000;"></div>
        <div style="display: flex; justify-content: space-between; margin-top: 3px;">
            <span>{int(min_feeders)}</span>
            <span>{int(max_feeders)}</span>
        </div>
        </div>
        '''
        m.get_root().html.add_child(folium.Element(colorbar_html))

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
    # Remove any values over 1 million (likely data errors)
    combined_data = combined_data[combined_data[y_column] <= 1_000_000].copy()

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
