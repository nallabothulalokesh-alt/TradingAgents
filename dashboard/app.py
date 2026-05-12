"""
dashboard/app.py — thin re-export so `streamlit run dashboard/app.py` still works.
All real logic lives in streamlit_app.py at the project root.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Re-run the canonical entry point
exec(open(ROOT / "streamlit_app.py").read())
