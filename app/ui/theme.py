"""Claro design tokens, global CSS, Plotly template and Colombian number formatting."""
from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# Palette (Claro signage manual).
RED = "#C22821"
GRAY = "#BDC3B8"
WHITE = "#FDFDFD"
BLACK = "#332F2E"
# Derived tints (text on white must stay AA: GRAY is for lines/fills only).
GRAY_LIGHT = "#F2F3F0"
GRAY_TEXT = "#5E5A58"
GRAY_MID = "#8C918A"
RED_DARK = "#9E1F19"
RED_LIGHT = "#F6DCDA"
GREEN = "#256B43"   # status only (validator OK); AA on GREEN_LIGHT
RED_ON_DARK = "#E8574E"  # brand red lifted to AA-large (3,7:1) on the dark band
GREEN_LIGHT = "#DCEFE3"

PALETTE = {"Rojo": RED, "Gris": GRAY, "Blanco": WHITE, "Negro": BLACK,
           "Gris claro": GRAY_LIGHT, "Gris texto": GRAY_TEXT, "Rojo oscuro": RED_DARK, "Rojo claro": RED_LIGHT,
           "Rojo sobre negro": RED_ON_DARK}

STATIC = Path(__file__).resolve().parent.parent / "static"
FONT_DIR = STATIC / "fonts"
BRAND_FONT = "Kamerik 105" if any(FONT_DIR.glob("Kamerik*")) else "Jost"
FONT_STACK = f"'{BRAND_FONT}', 'Jost', 'Segoe UI', sans-serif"


# ---------------------------------------------------------------- numbers (1.234,5)
def fmt_num(x, decimals: int = 0) -> str:
    if x is None:
        return "—"
    s = f"{float(x):,.{decimals}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_pct(x, decimals: int = 1) -> str:
    """``x`` in percentage points (99.7 -> '99,7 %')."""
    return "—" if x is None else f"{fmt_num(x, decimals)} %"


def fmt_delta(x, decimals: int = 0, suffix: str = "") -> str:
    if x is None:
        return ""
    sign = "+" if x > 0 else ("−" if x < 0 else "±")
    return f"{sign}{fmt_num(abs(x), decimals)}{suffix}"


# ---------------------------------------------------------------- plotly
def _register_plotly() -> None:
    layout = go.Layout(
        font=dict(family=FONT_STACK, color=BLACK, size=15),
        title=dict(font=dict(size=20, color=BLACK), x=0, xanchor="left"),
        colorway=[RED, BLACK, GRAY_MID, GRAY, "#E07B74", GRAY_TEXT],
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        separators=",.",
        xaxis=dict(showgrid=False, linecolor=GRAY, ticks="", zeroline=False, title=dict(standoff=8)),
        yaxis=dict(gridcolor=GRAY_LIGHT, linecolor=GRAY, zeroline=False, title=dict(standoff=8)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=dict(text="")),
        margin=dict(l=8, r=8, t=48, b=8),
        hoverlabel=dict(bgcolor=WHITE, bordercolor=GRAY, font=dict(family=FONT_STACK, color=BLACK)),
        bargap=0.25,
    )
    pio.templates["claro"] = go.layout.Template(layout=layout)
    pio.templates.default = "claro"


_register_plotly()


def highlight_colors(n: int, highlight: int | list[int] | None = 0) -> list[str]:
    """Red for the highlighted bars, gray for the rest (the manual's "one red thing" rule)."""
    hl = {highlight} if isinstance(highlight, int) else set(highlight or [])
    return [RED if i in hl else GRAY for i in range(n)]


# ---------------------------------------------------------------- CSS
CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Jost:wght@400;500;600;700;800&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,500,0..1,0&display=block');

:root {{
  --claro-red: {RED}; --claro-gray: {GRAY}; --claro-white: {WHITE}; --claro-black: {BLACK};
  --claro-gray-light: {GRAY_LIGHT}; --claro-gray-text: {GRAY_TEXT}; --claro-radius: 16px;
  --claro-shadow: 0 2px 6px rgba(51,47,46,.06), 0 8px 24px rgba(51,47,46,.08);
}}
html, body, [class*="st-"] {{ font-size: 16px; }}
.block-container {{ padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1320px; }}
small, .stCaption, [data-testid="stCaptionContainer"] {{ font-size: 15px !important; color: {GRAY_TEXT}; }}

.material-symbols-rounded {{
  font-family: 'Material Symbols Rounded'; font-weight: normal; font-style: normal; line-height: 1;
  letter-spacing: normal; text-transform: none; display: inline-block; white-space: nowrap;
  font-feature-settings: 'liga'; -webkit-font-smoothing: antialiased; vertical-align: middle;
  font-variation-settings: 'FILL' 1, 'wght' 500, 'GRAD' 0, 'opsz' 24;
}}

/* Buttons: pills; primary = solid red. */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{
  border-radius: 999px; font-weight: 600; letter-spacing: .02em; padding: .5rem 1.25rem;
}}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{
  background: {RED}; border-color: {RED}; color: {WHITE};
  box-shadow: 0 4px 14px rgba(194,40,33,.28);
}}
.stButton > button[kind="primary"]:hover {{ background: {RED_DARK}; border-color: {RED_DARK}; }}

/* Bordered containers become cards. */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {{ border-radius: var(--claro-radius); }}

/* Sidebar navigation: red underline on the active page. */
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] {{
  border-radius: 10px; padding: .3rem .6rem; border-bottom: 3px solid transparent;
}}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"],
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"].active {{
  border-bottom-color: {RED}; background: {WHITE}; font-weight: 700;
}}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] span {{ font-size: 15px; }}

/* Section label (uppercase, tracked). */
.claro-label {{
  text-transform: uppercase; letter-spacing: .14em; font-weight: 700; font-size: 15px; color: {GRAY_TEXT};
  margin: 1.6rem 0 .6rem; display: flex; align-items: center; gap: .6rem;
}}
.claro-label::after {{ content: ""; flex: 1; height: 1px; background: {GRAY}; }}
.claro-label.on-dark {{ color: {GRAY}; }}

/* Hero band (dark, huge numeral on the right). */
.claro-hero {{
  background: {BLACK}; color: {WHITE}; border-radius: 24px; padding: 2rem 2.4rem; margin-bottom: 1.4rem;
  display: flex; align-items: center; justify-content: space-between; gap: 2rem; overflow: hidden;
  position: relative;
}}
.claro-hero::before {{
  content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 10px; background: {RED};
}}
.claro-hero > div:first-child {{ flex: 1 1 auto; min-width: 0; }}
.claro-hero > div:last-child {{ flex: 0 0 auto; }}
.claro-hero h1 {{ color: {WHITE}; font-size: clamp(1.7rem, 2.6vw, 2.4rem); line-height: 1.1; margin: 0; padding: 0; font-weight: 800; }}
.claro-hero p {{ color: #E4E6E1; font-size: 1.1rem; margin: .6rem 0 0; max-width: 46rem; }}
.claro-hero .eyebrow {{ text-transform: uppercase; letter-spacing: .16em; font-size: 15px; color: {GRAY}; font-weight: 600; }}
.claro-hero .numeral {{
  font-size: clamp(3rem, 6.4vw, 7.5rem); font-weight: 800; line-height: .9; color: {RED_ON_DARK};
  letter-spacing: -.03em; white-space: nowrap; font-variant-numeric: tabular-nums;
}}
.claro-hero .numeral-caption {{ text-align: right; color: {GRAY}; text-transform: uppercase;
  letter-spacing: .14em; font-size: 15px; margin-top: .4rem; }}

/* KPI card. */
.claro-kpi {{
  background: {WHITE}; border-radius: var(--claro-radius); box-shadow: var(--claro-shadow);
  border: 1px solid {GRAY_LIGHT}; padding: 1.1rem 1.25rem 1rem; height: 100%;
}}
.claro-kpi .top {{ display: flex; align-items: center; justify-content: space-between; }}
.claro-kpi .lbl {{ text-transform: uppercase; letter-spacing: .08em; line-height: 1.25; font-size: 15px; color: {GRAY_TEXT}; font-weight: 600; }}
.claro-kpi .ico {{ color: {RED}; font-size: 28px; flex: 0 0 auto; }}
.claro-kpi .top {{ gap: .5rem; align-items: flex-start; }}
.claro-kpi .val {{ font-size: clamp(1.6rem, 2.3vw, 2.6rem); white-space: nowrap; font-weight: 800; color: {BLACK}; line-height: 1.1; margin-top: .35rem;
  font-variant-numeric: tabular-nums; letter-spacing: -.01em; }}
.claro-kpi .val.red {{ color: {RED}; }}
.claro-kpi .delta {{ font-size: 15px; font-weight: 600; margin-top: .25rem; }}
.claro-kpi .delta.up {{ color: {GREEN}; }} .claro-kpi .delta.down {{ color: {RED}; }} .claro-kpi .delta.flat {{ color: {GRAY_TEXT}; }}

/* Signage tile: white rounded square, red icon, uppercase label below. */
.claro-tiles {{ display: flex; flex-wrap: wrap; gap: 1.2rem; }}
.claro-tile {{ display: flex; flex-direction: column; align-items: center; width: 132px; text-decoration: none; }}
.claro-tile .sq {{
  width: 116px; height: 116px; border-radius: 26px; background: {WHITE}; box-shadow: var(--claro-shadow);
  border: 1px solid {GRAY_LIGHT}; display: flex; align-items: center; justify-content: center;
}}
.claro-tile .sq .material-symbols-rounded {{ font-size: 58px; color: {RED}; }}
.claro-tile .sq.ok .material-symbols-rounded {{ color: {GREEN}; }}
.claro-tile .sq.dark {{ background: {BLACK}; border-color: {BLACK}; }}
.claro-tile .sq.dark .material-symbols-rounded {{ color: {WHITE}; }}
.claro-tile .cap {{ margin-top: .7rem; text-transform: uppercase; letter-spacing: .1em; font-weight: 700;
  font-size: 15px; color: {BLACK}; text-align: center; line-height: 1.2; }}
.claro-tile .sub {{ font-size: 15px; color: {GRAY_TEXT}; text-align: center; }}

/* Chips and badges. */
.claro-chip {{ display: inline-flex; align-items: center; gap: .35rem; border-radius: 999px;
  padding: .18rem .7rem; font-size: 15px; font-weight: 600; border: 1.5px solid; margin: 0 .3rem .3rem 0;
  white-space: nowrap; }}
.claro-chip .material-symbols-rounded {{ font-size: 18px; }}
.claro-chip.on {{ border-color: {RED}; color: {RED}; background: {WHITE}; }}
.claro-chip.off {{ border-color: {GRAY}; color: {GRAY_TEXT}; background: {GRAY_LIGHT}; text-decoration: line-through; }}
.claro-chip.hit {{ border-color: {RED}; color: {WHITE}; background: {RED}; }}
.claro-chip.pass {{ border-color: {GREEN}; color: {GREEN}; background: {GREEN_LIGHT}; }}
.claro-badge {{ display: inline-flex; align-items: center; gap: .35rem; border-radius: 999px; padding: .2rem .8rem;
  font-size: 15px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; }}
.claro-badge.asignado {{ background: {RED}; color: {WHITE}; }}
.claro-badge.sin_accion {{ background: {GRAY_LIGHT}; color: {BLACK}; border: 1.5px solid {GRAY}; }}

/* Step header: huge red numeral + title. */
.claro-step {{ display: flex; align-items: center; gap: 1.1rem; margin: 1.8rem 0 .8rem; }}
.claro-step .n {{ font-size: 4.6rem; font-weight: 800; color: {RED}; line-height: .85; letter-spacing: -.04em;
  font-variant-numeric: tabular-nums; }}
.claro-step .t {{ font-size: 1.6rem; font-weight: 700; color: {BLACK}; line-height: 1.15; }}
.claro-step .s {{ font-size: 15px; color: {GRAY_TEXT}; text-transform: uppercase; letter-spacing: .12em; }}

/* Chunky rounded arrow (flow between steps). */
.claro-flow {{ display: flex; align-items: flex-start; flex-wrap: wrap; gap: .2rem; }}
.claro-flow .claro-tile {{ width: 112px; }}
.claro-flow .claro-tile .sq {{ width: 96px; height: 96px; border-radius: 22px; }}
.claro-flow .claro-tile .sq .material-symbols-rounded {{ font-size: 48px; }}
.claro-flow .claro-arrow {{ margin-top: 26px; }}
.claro-arrow {{ color: {RED}; font-size: 38px !important; font-variation-settings: 'FILL' 1, 'wght' 700 !important; }}

/* Unapplied-changes banner. */
.claro-banner {{ background: {RED_LIGHT}; border: 1.5px solid {RED}; color: {BLACK}; border-radius: 999px;
  padding: .55rem 1.2rem; display: flex; align-items: center; gap: .6rem; font-weight: 600; margin-bottom: .8rem; }}
.claro-banner .material-symbols-rounded {{ color: {RED}; }}

/* Swatch (style page). */
.claro-swatch {{ border-radius: var(--claro-radius); height: 96px; box-shadow: var(--claro-shadow);
  border: 1px solid {GRAY_LIGHT}; }}
.claro-swatch-cap {{ font-weight: 700; margin-top: .5rem; }} .claro-swatch-hex {{ color: {GRAY_TEXT}; font-size: 15px; }}

/* Sidebar meta block. */
.claro-meta {{ font-size: 15px; color: {GRAY_TEXT}; line-height: 1.5; }}
.claro-meta b {{ color: {BLACK}; }}
.claro-meta code {{ background: {WHITE}; color: {BLACK}; border-radius: 6px; padding: 0 .3rem; }}
</style>
"""


def inject_css() -> None:
    st.html(CSS)
