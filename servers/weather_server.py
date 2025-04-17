# Based on the MCP Python SDK Quickstart Example
# NOTE: This is a simplified version for local testing.
# Needs httpx: pip install httpx

from typing import Any
import httpx
from mcp.server.fastmcp import FastMCP
from urllib.parse import urljoin

# Initialize FastMCP server
mcp = FastMCP("weather")

# Single global HTTP client for re-use
_http_client = httpx.AsyncClient(follow_redirects=True, timeout=30.0)

# Constants
NWS_API_BASE = "https://api.weather.gov"
USER_AGENT = "mcp-bridge-test-app/1.0 (test@example.com)"  # Use a descriptive agent, maybe your email


async def make_nws_request(url: str) -> dict[str, Any] | None:
    """Make a request to the NWS API with proper error handling using a shared HTTP client."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/geo+json",
    }
    try:
        print(f"[WeatherServer] Making request to: {url}")
        response = await _http_client.get(url, headers=headers)
        response.raise_for_status()
        print(f"[WeatherServer] Request successful, status: {response.status_code}")
        return response.json()
    except httpx.RequestError as exc:
        print(f"[WeatherServer] Request error for {exc.request.url!r}: {exc}")
    except httpx.HTTPStatusError as exc:
        print(
            f"[WeatherServer] HTTP error {exc.response.status_code} for {exc.request.url!r}: {exc.response.text}"
        )
    except Exception as e:
        print(f"[WeatherServer] Unexpected error: {e}")
    return None


def format_alert(feature: dict) -> str:
    """Format an alert feature into a readable string."""
    try:
        props = feature["properties"]
        return f"""
Event: {props.get('event', 'Unknown')}
Area: {props.get('areaDesc', 'Unknown')}
Severity: {props.get('severity', 'Unknown')}
Description: {props.get('description', 'No description available')}
Instructions: {props.get('instruction', 'No specific instructions provided')}
"""
    except KeyError as e:
        print(f"[WeatherServer] Missing key in alert properties: {e}")
        return "Error formatting alert: Missing data."
    except Exception as e:
        print(f"[WeatherServer] Error formatting alert: {e}")
        return "Error formatting alert."


@mcp.tool()
async def get_alerts(state: str) -> str:
    """Get weather alerts for a US state.

    Args:
        state: Two-letter US state code (e.g. CA, NY)
    """
    print(f"[WeatherServer] Executing tool: get_alerts(state='{state}')")
    # Build the URL safely
    relative = f"/alerts/active/area/{state.upper()}"
    url = urljoin(NWS_API_BASE, relative)
    print(f"[WeatherServer] get_alerts URL: {url}")
    data = await make_nws_request(url)

    if not data or "features" not in data:
        return "Unable to fetch alerts or no alerts found for this state."

    if not data["features"]:
        return f"No active alerts found for {state.upper()}."

    try:
        alerts = [format_alert(feature) for feature in data["features"]]
        response = "\n---\n".join(alerts)
        print(f"[WeatherServer] get_alerts response generated ({len(alerts)} alerts).")
        return response if response else "No alerts formatted."
    except Exception as e:
        print(f"[WeatherServer] Error processing alerts: {e}")
        return "Error processing alerts data."


@mcp.tool()
async def get_forecast(latitude: float, longitude: float) -> str:
    """Get weather forecast for a specific latitude/longitude.

    Args:
        latitude: Latitude of the location
        longitude: Longitude of the location
    """
    print(
        f"[WeatherServer] Executing tool: get_forecast(latitude={latitude}, longitude={longitude})"
    )
    # First get the gridpoint
    relative_pts = f"/points/{latitude:.4f},{longitude:.4f}"
    points_url = urljoin(NWS_API_BASE, relative_pts)
    print(f"[WeatherServer] get_forecast points URL: {points_url}")
    points_data = await make_nws_request(points_url)

    if not (
        points_data
        and "properties" in points_data
        and "forecast" in points_data["properties"]
    ):
        return "Unable to get forecast grid point for this location."

    forecast_url = points_data["properties"]["forecast"]
    # Make sure forecast_url is absolute; if it's relative, join again
    full_forecast_url = (
        urljoin(NWS_API_BASE, forecast_url)
        if forecast_url.startswith("/")
        else forecast_url
    )
    print(f"[WeatherServer] get_forecast forecast URL: {full_forecast_url}")
    forecast_data = await make_nws_request(full_forecast_url)

    if (
        not forecast_data
        or "properties" not in forecast_data
        or "periods" not in forecast_data["properties"]
    ):
        return "Unable to fetch detailed forecast data."

    try:
        periods = forecast_data["properties"]["periods"]
        # Let's format the next 3 periods for brevity
        forecasts = []
        for period in periods[:3]:
            forecast = f"""
{period.get('name', 'Unknown Period')}:
Temperature: {period.get('temperature', 'N/A')}°{period.get('temperatureUnit', 'F')}
Wind: {period.get('windSpeed', 'N/A')} {period.get('windDirection', 'N/A')}
Forecast: {period.get('shortForecast', 'No short forecast available')}
"""
            # Use detailedForecast if you want more text:
            # Forecast: {period.get('detailedForecast', 'No detailed forecast available')}
            forecasts.append(forecast.strip())

        response = "\n---\n".join(forecasts)
        print(
            f"[WeatherServer] get_forecast response generated ({len(forecasts)} periods)."
        )
        return response if response else "No forecast periods found."
    except Exception as e:
        print(f"[WeatherServer] Error processing forecast periods: {e}")
        return "Error processing forecast data."


if __name__ == "__main__":
    print("[WeatherServer] Starting MCP Weather Server via stdio...")
    # Run the server using stdio transport
    mcp.run(transport="stdio")
    print("[WeatherServer] MCP Weather Server stopped.")
