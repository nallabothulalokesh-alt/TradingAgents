"""
TradingAgents Streamlit Application — single entry point.
All nav, CSS and routing live here; dashboard/app.py imports from this module.
"""

import streamlit as st
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from dashboard.views.single_ticker import render_single_ticker
from dashboard.views.watchlist import render_watchlist
from dashboard.views.portfolio import render_portfolio
from dashboard.views.history import render_history
from dashboard.views.chat import render_chat

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TradingAgents Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    div[data-testid="stSidebarNav"] { display: none; }
    .badge-buy        { background:#16a34a; color:#fff; padding:3px 10px; border-radius:12px; font-weight:700; font-size:13px; }
    .badge-overweight { background:#4ade80; color:#14532d; padding:3px 10px; border-radius:12px; font-weight:700; font-size:13px; }
    .badge-hold       { background:#ca8a04; color:#fff; padding:3px 10px; border-radius:12px; font-weight:700; font-size:13px; }
    .badge-underweight{ background:#f97316; color:#fff; padding:3px 10px; border-radius:12px; font-weight:700; font-size:13px; }
    .badge-sell       { background:#dc2626; color:#fff; padding:3px 10px; border-radius:12px; font-weight:700; font-size:13px; }
    .pill-pending    { background:#374151; color:#9ca3af; padding:2px 8px; border-radius:10px; font-size:12px; }
    .pill-running    { background:#1d4ed8; color:#fff;    padding:2px 8px; border-radius:10px; font-size:12px; }
    .pill-done       { background:#15803d; color:#fff;    padding:2px 8px; border-radius:10px; font-size:12px; }
    .pill-error      { background:#b91c1c; color:#fff;    padding:2px 8px; border-radius:10px; font-size:12px; }
    .metric-card     { background:#1e293b; border-radius:10px; padding:16px 20px; margin-bottom:8px; }
    .section-header  { font-size:18px; font-weight:700; margin:20px 0 10px 0; border-bottom:1px solid #334155; padding-bottom:6px; }
</style>
""", unsafe_allow_html=True)

_NAV_OPTIONS = [
    "🔍 Single Ticker",
    "📊 Multi-Ticker Analysis",
    "💼 Portfolio",
    "📜 History",
    "💬 Analysis Chat",
]

# Apply pending navigation before the widget renders
if "_nav_target" in st.session_state:
    st.session_state["main_nav"] = st.session_state.pop("_nav_target")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📈 TradingAgents")
    st.markdown("*Multi-Agent LLM Trading Framework*")
    st.divider()
    view = st.radio("Navigation", _NAV_OPTIONS,
                    label_visibility="collapsed", key="main_nav")
    st.divider()
    st.caption("Powered by LangGraph + yfinance")

# ── Route ─────────────────────────────────────────────────────────────────────
if view == "🔍 Single Ticker":
    render_single_ticker()
elif view == "📊 Multi-Ticker Analysis":
    render_watchlist()
elif view == "💼 Portfolio":
    render_portfolio()
elif view == "📜 History":
    render_history()
elif view == "💬 Analysis Chat":
    render_chat()
