# UK-power-market-dashboard

This project provides a simple, interactive dashboard for exploring the UK power system using publicly available data from the Elexon BMRS Insights API. It visualises the generation mix across different fuel categories, estimates the resulting carbon intensity of the electricity grid, and compares supply against forecast demand on a half‑hourly basis.
<img width="698" height="745" alt="image" src="https://github.com/user-attachments/assets/4b55c533-b16e-4252-ba43-8d13c24dbe7f" align=center />


# Features

Automated data retrieval — The script downloads recent instantaneous generation (FUELINST) and total system demand forecast (TSDF) datasets directly from Elexon's API. No API key is required to access these endpoints.

Data processing — Raw data is cleaned, fuel types are grouped into broader categories (Gas, Biomass, Nuclear, Wind, Hydro, Imports and Coal/Oil/Other), and carbon intensity is estimated using typical emissions factors taken from National Grid's methodology
nationalgrid.com
.

Interactive visualisations — The dashboard uses Dash and Plotly to display:

A stacked area chart of generation by fuel category.

A line chart showing estimated carbon intensity (g CO₂/kWh).

A supply minus demand line chart (if overlapping periods exist) to highlight potential imbalances between generation and forecast demand.

Easy deployment — All logic is contained in a single Python script. Running it locally will spin up a web server and open the dashboard in your browser.

# Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

# Prerequisites

You will need Python 3.9 or later. Install the required dependencies:

pip install -r requirements.txt

Running the Dashboard

To start the dashboard, execute:

python power_market_dashboard.py


The script will fetch fresh data from Elexon, process it and launch a Dash server. By default, the app runs on http://127.0.0.1:8050. Open this URL in your browser to interact with the charts.

If the API is unreachable (for example, due to local network restrictions), the script will look for fallback files FUELINST.csv and TSDF.json in the same directory. You can provide your own copies of these datasets to enable the dashboard to work offline. Otherwise, a descriptive error will be raised.

# Notes

Data freshness — Elexon's FUELINST and TSDF endpoints provide near real‑time information. When you run the script, it downloads the most recently published intervals. No historical date filtering is implemented because Elexon's API currently returns only recent data without specifying time ranges.

Supply vs demand — The dashboard attempts to merge generation and demand data on half‑hour boundaries. If there is no overlap between the most recent FUELINST and TSDF periods, the supply–demand chart will be omitted.

Carbon intensity assumptions — Emission factors are approximate values drawn from National Grid's carbon intensity calculations
nationalgrid.com
. They should not be used for official reporting.

# License

This project is provided for educational and demonstration purposes. It carries no warranty and is not associated with or endorsed by Elexon or National Grid.
