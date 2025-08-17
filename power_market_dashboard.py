"""
Power Market Dashboard
=======================

This script builds an interactive dashboard for exploring the UK power market
using open data published by Elexon (BMRS).  It downloads recent
generation out‑turn by fuel type (`FUELINST`) and total system demand
forecast (`TSDF`) from the Insights Solution API, cleans and aggregates
the data, estimates carbon intensity based on typical emissions factors,
and serves a simple Dash application with two interactive charts.

**Usage:**

    python power_market_dashboard.py

Then open the provided local URL (e.g. http://127.0.0.1:8050) in your
browser to explore the dashboard.  The script does not require an
Elexon API key but relies on public dataset endpoints.

**Key features:**
* Fetches instantaneous generation out‑turn and demand forecast data
  directly from Elexon's API.
* Categorises generation into Gas, Biomass, Nuclear, Wind, Hydro,
  Imports and Coal/Oil/Other.
* Estimates carbon intensity using emissions factors taken from
  National Grid’s methodology【294358803913953†L240-L246】.
* Presents an interactive stacked area chart for generation mix and a
  line chart for carbon intensity using Plotly.

Note: Running this script requires `dash`, `pandas`, `plotly` and
`requests`.  Install missing packages with `pip install dash pandas plotly
requests`.
"""

import datetime as _dt
from typing import Tuple, Dict

import pandas as pd  # type: ignore
import requests  # type: ignore
import json as _json  # used for fallback parsing
import os  # used to locate fallback files

# Plotly and Dash imports
import plotly.express as px  # type: ignore
from dash import Dash, dcc, html  # type: ignore


def fetch_fuelinst_data() -> pd.DataFrame:
    """Fetches the latest instantaneous generation out‑turn by fuel type
    from Elexon's Insights Solution API.

    The endpoint returns data for the most recently published 5‑minute
    intervals.  If the request fails, a ValueError is raised.

    Returns
    -------
    pandas.DataFrame
        A DataFrame with columns including 'dataset', 'publishTime',
        'startTime', 'settlementDate', 'settlementPeriod', 'fuelType'
        and 'generation'.
    """
    url = "https://data.elexon.co.uk/bmrs/api/v1/datasets/FUELINST"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; PowerMarketDashboard/1.0)"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json().get("data", [])
        if not data:
            raise ValueError("No FUELINST data returned from API.")
        df = pd.DataFrame(data)
    else:
        # Attempt to use local fallback file if API call fails
        fallback_path = os.path.join(os.path.dirname(__file__), "FUELINST.csv")
        if os.path.exists(fallback_path):
            df = pd.read_csv(fallback_path)
        else:
            raise ValueError(
                f"Failed to fetch FUELINST data (HTTP {response.status_code}) and no local fallback available."
            )
    # Standardise column names
    df.rename(
        columns={
            "dataset": "Dataset",
            "publishTime": "PublishTime",
            "startTime": "StartTime",
            "settlementDate": "SettlementDate",
            "settlementPeriod": "SettlementPeriod",
            "fuelType": "FuelType",
            "generation": "Generation",
        },
        inplace=True,
    )
    return df


def fetch_tsdf_data() -> pd.DataFrame:
    """Fetches the total system demand forecast (TSDF) data from Elexon's
    Insights Solution API.

    The endpoint returns half‑hourly demand forecasts for the upcoming
    periods.  If the request fails, a ValueError is raised.

    Returns
    -------
    pandas.DataFrame
        A DataFrame with columns including 'dataset', 'demand',
        'publishTime', 'startTime', 'settlementDate', 'settlementPeriod'
        and 'boundary'.
    """
    url = "https://data.elexon.co.uk/bmrs/api/v1/datasets/TSDF"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; PowerMarketDashboard/1.0)"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json().get("data", [])
        if not data:
            raise ValueError("No TSDF data returned from API.")
        df = pd.DataFrame(data)
    else:
        fallback_path = os.path.join(os.path.dirname(__file__), "TSDF.json")
        if os.path.exists(fallback_path):
            # Parse JSON file (list of records under key 'data')
            with open(fallback_path, "r", encoding="utf-8") as f:
                fallback_data = _json.load(f)
            # Some files store data as top-level list; others under 'data'
            if isinstance(fallback_data, dict) and "data" in fallback_data:
                fallback_data = fallback_data["data"]
            df = pd.DataFrame(fallback_data)
        else:
            raise ValueError(
                f"Failed to fetch TSDF data (HTTP {response.status_code}) and no local fallback available."
            )
    # Standardise column names
    df.rename(
        columns={
            "dataset": "Dataset",
            "publishTime": "PublishTime",
            "startTime": "StartTime",
            "settlementDate": "SettlementDate",
            "settlementPeriod": "SettlementPeriod",
            "boundary": "Boundary",
        },
        inplace=True,
    )
    return df


def _categorise_fuel_types(fuel_type: str) -> str:
    """Maps raw fuel type identifiers into broader categories.

    Parameters
    ----------
    fuel_type : str
        Raw fuel type name from FUELINST (e.g. 'CCGT', 'INTELEC').

    Returns
    -------
    str
        High‑level category name.
    """
    category_map: Dict[str, str] = {
        # Gas generation (combined and open cycle)
        "CCGT": "Gas",
        "OCGT": "Gas",
        # Biomass
        "BIOMASS": "Biomass",
        # Fossil/other
        "COAL": "Coal/Oil/Other",
        "OIL": "Coal/Oil/Other",
        "OTHER": "Coal/Oil/Other",
        # Nuclear
        "NUCLEAR": "Nuclear",
        # Wind
        "WIND": "Wind",
        # Hydro and pumped storage
        "NPSHYD": "Hydro",
        "PS": "Hydro",
    }
    interconnectors = {
        "INTELEC",
        "INTEW",
        "INTFR",
        "INTGRNL",
        "INTIFA2",
        "INTIRL",
        "INTNED",
        "INTNEM",
        "INTNSL",
        "INTVKL",
    }
    if fuel_type in category_map:
        return category_map[fuel_type]
    if fuel_type in interconnectors:
        return "Imports"
    # Fallback: lump any unknown category into 'Other'
    return "Coal/Oil/Other"


def process_data(
    fuel_df: pd.DataFrame, tsdf_df: pd.DataFrame
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Cleans and aggregates the downloaded datasets.

    The processing pipeline performs the following steps:

    * Convert timestamps to timezone‑aware datetimes (Europe/London).
    * Clip negative generation values (e.g. pumped storage consumption) to zero.
    * Categorise fuel types into broader groups.
    * Aggregate instantaneous generation into a pivot table for plotting.
    * Estimate carbon intensity (gCO₂/kWh) at each timestamp using
      default emissions factors【294358803913953†L240-L246】.
    * Aggregate half‑hourly total generation and merge with demand forecasts
      for potential supply‑vs‑demand analysis.

    Parameters
    ----------
    fuel_df : pandas.DataFrame
        Raw FUELINST data returned by `fetch_fuelinst_data()`.
    tsdf_df : pandas.DataFrame
        Raw TSDF data returned by `fetch_tsdf_data()`.

    Returns
    -------
    Tuple[pandas.DataFrame, pandas.DataFrame, pandas.DataFrame]
        1. A pivoted DataFrame indexed by local time with columns for
           each fuel category and additional 'TotalGeneration' and
           'CarbonIntensity'.
        2. A long‑format DataFrame for the stacked area chart.
        3. A merged DataFrame containing half‑hourly total generation and
           demand values (may be empty if periods do not overlap).
    """
    # Convert StartTime to datetime
    fuel_df["StartTime"] = pd.to_datetime(fuel_df["StartTime"], utc=True)
    # Create local time column
    fuel_df["LocalTime"] = fuel_df["StartTime"].dt.tz_convert("Europe/London")
    # Clip negative generation
    fuel_df["Generation_clipped"] = fuel_df["Generation"].clip(lower=0)
    # Categorise fuel types
    fuel_df["Category"] = fuel_df["FuelType"].apply(_categorise_fuel_types)
    # Pivot table by 5‑minute intervals
    pivot = fuel_df.pivot_table(
        index="LocalTime",
        columns="Category",
        values="Generation_clipped",
        aggfunc="sum",
    ).fillna(0)
    # Ensure all expected columns exist
    for col in ["Gas", "Biomass", "Nuclear", "Wind", "Hydro", "Imports", "Coal/Oil/Other"]:
        if col not in pivot.columns:
            pivot[col] = 0.0
    # Total generation
    pivot["TotalGeneration"] = pivot[[
        "Gas", "Biomass", "Nuclear", "Wind", "Hydro", "Imports", "Coal/Oil/Other",
    ]].sum(axis=1)
    # Emission factors (g/kWh)
    emission_factors: Dict[str, float] = {
        "Gas": 329.4,        # 0.3294 t/MWh -> 329.4 g/kWh【294358803913953†L240-L246】
        "Biomass": 120.0,    # 0.12 t/MWh -> 120 g/kWh【294358803913953†L240-L246】
        "Coal/Oil/Other": 675.0,  # approximate using oil factor【294358803913953†L240-L246】
        "Nuclear": 0.0,
        "Wind": 0.0,
        "Hydro": 0.0,
        "Imports": 329.4,   # assume gas‑like mix for imports
    }
    # Calculate carbon intensity
    ci_numerator = pd.Series(0.0, index=pivot.index)
    for cat, ef in emission_factors.items():
        ci_numerator += pivot[cat] * ef
    pivot["CarbonIntensity"] = ci_numerator / pivot["TotalGeneration"].replace(0, pd.NA)
    # Long format for stacked area
    area_df = pivot[
        ["Gas", "Biomass", "Nuclear", "Wind", "Hydro", "Imports", "Coal/Oil/Other"]
    ].reset_index().melt(id_vars="LocalTime", var_name="Category", value_name="Generation")
    # Prepare demand merge (half‑hour resolution)
    fuel_df["LocalHalfHour"] = fuel_df["LocalTime"].dt.floor("30min")
    half_hour_gen = (
        fuel_df.groupby("LocalHalfHour")["Generation_clipped"].sum().reset_index()
    )
    # TSDF local time
    tsdf_df["StartTime"] = pd.to_datetime(tsdf_df["StartTime"], utc=True)
    tsdf_df["LocalTime"] = tsdf_df["StartTime"].dt.tz_convert("Europe/London")
    tsdf_df["LocalHalfHour"] = tsdf_df["LocalTime"].dt.floor("30min")
    # Use latest demand per half‑hour window (greatest publish time)
    latest_tsdf = (
        tsdf_df.sort_values("PublishTime").groupby("LocalHalfHour").tail(1)
    )
    demand_merge = pd.merge(
        latest_tsdf[["LocalHalfHour", "demand"]],
        half_hour_gen,
        on="LocalHalfHour",
        how="inner",
    )
    demand_merge.rename(
        columns={
            "Generation_clipped": "TotalGeneration",
            "demand": "DemandForecast",
        },
        inplace=True,
    )
    demand_merge["SupplyMinusDemand"] = (
        demand_merge["TotalGeneration"] - demand_merge["DemandForecast"]
    )
    return pivot, area_df, demand_merge


def create_dashboard(
    area_df: pd.DataFrame,
    pivot_df: pd.DataFrame,
    demand_df: pd.DataFrame | None = None,
) -> Dash:
    """Creates a Dash application with interactive charts.

    Parameters
    ----------
    area_df : pandas.DataFrame
        Long‑format data frame with generation values by category and
        timestamp.
    pivot_df : pandas.DataFrame
        Pivot table containing carbon intensity and total generation.
    demand_df : pandas.DataFrame | None, optional
        Data frame with half‑hourly total generation, demand forecast and
        supply minus demand.  If provided and non‑empty, an additional
        line chart will be included showing the supply‑demand balance.

    Returns
    -------
    dash.Dash
        A Dash app ready to be served.
    """
    app = Dash(__name__)
    # Stacked area chart (generation mix)
    area_fig = px.area(
        area_df,
        x="LocalTime",
        y="Generation",
        color="Category",
        title="Generation Mix by Fuel Category",
        labels={
            "LocalTime": "Time (Europe/London)",
            "Generation": "Generation (MW)",
        },
    )
    area_fig.update_layout(legend_title_text="Category")
    # Carbon intensity line chart
    ci_fig = px.line(
        pivot_df.reset_index(),
        x="LocalTime",
        y="CarbonIntensity",
        title="Estimated Carbon Intensity",
        labels={
            "LocalTime": "Time (Europe/London)",
            "CarbonIntensity": "Carbon Intensity (g/kWh)",
        },
    )
    # set y-axis range to add headroom
    ci_max = pivot_df["CarbonIntensity"].max()
    if pd.notna(ci_max) and ci_max > 0:
        ci_fig.update_layout(yaxis_range=[0, ci_max * 1.1])
    # Optionally create supply‑demand chart
    charts = [dcc.Graph(figure=area_fig), dcc.Graph(figure=ci_fig)]
    if demand_df is not None and not demand_df.empty:
        sd_fig = px.line(
            demand_df,
            x="LocalHalfHour",
            y="SupplyMinusDemand",
            title="Supply Minus Demand (Half‑hourly)",
            labels={
                "LocalHalfHour": "Time (Europe/London)",
                "SupplyMinusDemand": "Supply − Demand (MW)",
            },
        )
        sd_fig.update_layout(
            yaxis_title="Supply − Demand (MW)",
            xaxis_title="Time (Europe/London)",
        )
        charts.append(dcc.Graph(figure=sd_fig))
    # Build layout
    app.layout = html.Div(
        [
            html.H1("UK Power Market Dashboard"),
            html.P(
                "This dashboard shows the UK power generation mix, estimated carbon "
                "intensity and supply‑demand balance using open data from Elexon."
            ),
        ]
        + charts
    )
    return app


def main() -> None:
    """Entry point when running this script as a module."""
    print("Fetching data from Elexon…")
    fuel_df = fetch_fuelinst_data()
    tsdf_df = fetch_tsdf_data()
    print(
        f"Retrieved {len(fuel_df)} rows of FUELINST data and "
        f"{len(tsdf_df)} rows of TSDF data."
    )
    print("Processing data…")
    pivot_df, area_df, demand_merge = process_data(fuel_df, tsdf_df)
    if demand_merge.empty:
        print(
            "Warning: no overlapping half‑hour periods between generation and "
            "demand forecast. Supply‑versus‑demand analysis will be empty."
        )
    else:
        avg_diff = demand_merge["SupplyMinusDemand"].mean()
        print(
            f"Average supply minus forecast demand (MW) for overlap: {avg_diff:.1f}"
        )
    # Pass demand_merge to dashboard for supply/demand chart
    app = create_dashboard(area_df, pivot_df, demand_merge if not demand_merge.empty else None)
    # Run the Dash server
    print("Starting dashboard… Navigate to http://127.0.0.1:8050 in your browser.")
    app.run_server(debug=False)


if __name__ == "__main__":
    main()