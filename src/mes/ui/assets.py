"""Template-backed HTML renderer for the MES control room."""

from functools import lru_cache
from pathlib import Path


UI_ROOT = Path(__file__).resolve().parent
TEMPLATE_PATH = UI_ROOT / "templates" / "control_room.html"
CSS_PATH = UI_ROOT / "static" / "control_room.css"
JS_PATH = UI_ROOT / "static" / "control_room.js"


@lru_cache(maxsize=1)
def control_room_html() -> str:
    """Render the control room as a single HTML document for the existing route."""
    template = TEMPLATE_PATH.read_text()
    css = CSS_PATH.read_text()
    js = JS_PATH.read_text()
    return (
        template.replace("{{ control_room_css }}", css)
        .replace("{{ control_room_js }}", js)
    )
