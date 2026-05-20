"""Interactive execution-quality dashboard for the demo or a ledger API."""

import json
import os
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd
import streamlit as st

from post_trade.events import AlertLimits
from post_trade.execution import build_execution_report
from post_trade.exports import orders_csv
from post_trade.fixtures import demo_batch
from post_trade.scope import ReportScope

st.set_page_config(page_title="Execution Quality", layout="wide")
st.title("Execution Quality")
api_url = os.getenv("EXECUTION_API", "http://127.0.0.1:8000").rstrip("/")
options = ["Ledger API", "Synthetic replay"] if os.getenv("EXECUTION_API") else ["Synthetic replay", "Ledger API"]
source = st.sidebar.radio("Data source", options)
limits = AlertLimits(
    slippage_bps=st.sidebar.number_input("Adverse slippage limit (bps)", min_value=0, max_value=100_000, value=40),
    latency_ms=st.sidebar.number_input("Latency limit (ms)", min_value=1, max_value=1_000_000, value=1_000),
    missing_after_ms=st.sidebar.number_input("Missing fill after (ms)", min_value=1, max_value=1_000_000, value=5_000),
)
try:
    scope = ReportScope(
        venue=st.sidebar.text_input("Venue filter").strip() or None,
        route=st.sidebar.text_input("Route filter").strip() or None,
        symbol=st.sidebar.text_input("Symbol filter").strip() or None,
    )
except ValueError as exc:
    st.error(f"Invalid report filter. {exc}")
    st.stop()
if source == "Ledger API":
    as_of = st.sidebar.text_input("Replay cutoff (ISO-8601 with timezone)")
    params = {**limits.model_dump(), **scope.model_dump(exclude_none=True)}
    if as_of:
        params["as_of"] = as_of
    try:
        with urlopen(f"{api_url}/v1/report?{urlencode(params)}", timeout=10) as response:
            report = json.load(response)
    except (OSError, ValueError) as exc:
        st.error(f"Ledger API request failed. {exc}")
        st.stop()
else:
    report = build_execution_report(demo_batch(), limits=limits, scope=scope)

st.caption(f"Replay as of {report['as_of']}")
summary = report["summary"]
orders, pnl, latency, alerts = st.columns(4)
orders.metric("Orders", summary["orders"])
pnl.metric("Execution P&L (USD)", f"{summary['execution_pnl_usd']:.2f}")
p95 = summary["p95_latency_ms"]
latency.metric("P95 latency", f"{p95:,.0f} ms" if p95 is not None else "—")
alerts.metric("Alerts", len(report["alerts"]))
cost_tab, orders_tab, inventory_tab, alerts_tab = st.tabs(["Venue analytics", "Orders", "Inventory", "Alerts"])
with cost_tab:
    venues = pd.DataFrame.from_dict(report["by_venue"], orient="index")
    if venues.empty:
        st.info("Ingest execution events to view venue analytics.")
    else:
        st.bar_chart(venues[["gas_usd", "fee_usd"]], y_label="USD")
        st.bar_chart(venues["p95_latency_ms"].rename("P95 latency (ms)"), y_label="Milliseconds")
        st.dataframe(pd.DataFrame.from_dict(report["by_route"], orient="index"))
with orders_tab:
    st.dataframe(report["orders"], hide_index=True)
    st.download_button("Download orders CSV", orders_csv(report["orders"]), "orders.csv", "text/csv")
with inventory_tab:
    st.dataframe(pd.DataFrame.from_dict(report["by_symbol"], orient="index"))
with alerts_tab:
    st.dataframe(report["alerts"], hide_index=True)
    st.subheader("Quarantined receipts")
    st.dataframe(report["unlinked_receipts"], hide_index=True)
st.download_button("Download report", json.dumps(report, indent=2), "execution-report.json", "application/json")
