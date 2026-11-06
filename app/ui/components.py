"""Reusable signage-style components (HTML + the CSS classes injected by theme.inject_css)."""
from __future__ import annotations

from html import escape

import streamlit as st

from app.ui.theme import fmt_delta


def icon(name: str, cls: str = "") -> str:
    """Material Symbols Rounded glyph by ligature name, e.g. icon('campaign')."""
    return f'<span class="material-symbols-rounded {cls}" aria-hidden="true">{escape(name)}</span>'


def section_label(text: str, on_dark: bool = False) -> None:
    st.html(f'<div class="claro-label{" on-dark" if on_dark else ""}">{escape(text)}</div>')


def hero(title: str, subtitle: str = "", big_numeral: str | None = None, eyebrow: str = "",
         numeral_caption: str = "") -> None:
    """Dark band with title at left and a huge red numeral at right (manual's section opener)."""
    right = ""
    if big_numeral is not None:
        cap = f'<div class="numeral-caption">{escape(numeral_caption)}</div>' if numeral_caption else ""
        right = f'<div><div class="numeral">{escape(str(big_numeral))}</div>{cap}</div>'
    eb = f'<div class="eyebrow">{escape(eyebrow)}</div>' if eyebrow else ""
    sub = f"<p>{escape(subtitle)}</p>" if subtitle else ""
    st.html(f'<div class="claro-hero"><div>{eb}<h1>{escape(title)}</h1>{sub}</div>{right}</div>')


def kpi_card_html(label: str, value: str, delta_vs_baseline: float | None = None, icon_name: str = "",
                  delta_text: str | None = None, higher_is_better: bool = True, emphasis: bool = False,
                  decimals: int = 0) -> str:
    delta = ""
    if delta_vs_baseline is not None or delta_text:
        d = round(delta_vs_baseline or 0.0, decimals)  # -0,02 shown with 1 decimal is a tie
        good = (d > 0) == higher_is_better
        cls = "flat" if abs(d) < 1e-9 else ("up" if good else "down")
        arrow = "trending_flat" if cls == "flat" else ("trending_up" if d > 0 else "trending_down")
        text = delta_text or f"{fmt_delta(d, decimals)} vs. línea base"
        delta = f'<div class="delta {cls}">{icon(arrow)} {escape(text)}</div>'
    ico = icon(icon_name, "ico") if icon_name else ""
    return (f'<div class="claro-kpi"><div class="top"><span class="lbl">{escape(label)}</span>{ico}</div>'
            f'<div class="val{" red" if emphasis else ""}">{escape(value)}</div>{delta}</div>')


def kpi_card(label: str, value: str, delta_vs_baseline: float | None = None, icon_name: str = "", **kw) -> None:
    st.html(kpi_card_html(label, value, delta_vs_baseline, icon_name, **kw))


def kpi_row(cards: list[dict], per_row: int | None = None) -> None:
    """Cards in equal columns; ``per_row`` wraps long rows so values never overflow at 1366 px."""
    per_row = per_row or len(cards)
    for start in range(0, len(cards), per_row):
        chunk = cards[start:start + per_row]
        for col, card in zip(st.columns(per_row), chunk):
            with col:
                kpi_card(**card)


def tile_html(icon_name: str, label: str, sub: str = "", state: str = "", small: bool = False) -> str:
    """White rounded square, red icon, uppercase label below. state: '' | 'ok' | 'dark'."""
    s = f'<div class="sub">{escape(sub)}</div>' if sub else ""
    return (f'<div class="claro-tile{" sm" if small else ""}"><div class="sq {state}">{icon(icon_name)}</div>'
            f'<div class="cap">{escape(label)}</div>{s}</div>')


def tile(icon_name: str, label: str, sub: str = "", state: str = "") -> None:
    st.html(tile_html(icon_name, label, sub, state))


def tiles(items: list[dict]) -> None:
    st.html('<div class="claro-tiles">' + "".join(tile_html(**i) for i in items) + "</div>")


RULE_STATES = {"on": "toggle_on", "off": "toggle_off", "hit": "block", "pass": "check_circle"}


def rule_chip_html(rule_id: str, state: str = "on", label: str = "") -> str:
    """state: on (active rule) | off (inactive) | hit (excluded this case) | pass (rule satisfied)."""
    text = escape(rule_id) + (f" · {escape(label)}" if label else "")
    return f'<span class="claro-chip {state}">{icon(RULE_STATES.get(state, "rule"))}{text}</span>'


def rule_chip(rule_id: str, state: str = "on", label: str = "") -> None:
    st.html(rule_chip_html(rule_id, state, label))


def chip_html(text: str, icon_name: str = "", state: str = "on") -> str:
    """Plain pill (no on/off meaning), e.g. a channel name."""
    return f'<span class="claro-chip {state}">{icon(icon_name) if icon_name else ""}{escape(text)}</span>'


def status_badge_html(estado: str) -> str:
    label, ico = {"asignado": ("Asignado", "check"), "sin_accion": ("Sin acción", "remove")}.get(
        estado, (estado, "help"))
    return f'<span class="claro-badge {escape(estado)}">{icon(ico)}{label}</span>'


def status_badge(estado: str) -> None:
    st.html(status_badge_html(estado))


def step_header(n: int | str, title: str, subtitle: str = "") -> None:
    sub = f'<div class="s">{escape(subtitle)}</div>' if subtitle else ""
    st.html(f'<div class="claro-step"><div class="n">{escape(str(n))}</div>'
            f'<div>{sub}<div class="t">{escape(title)}</div></div></div>')


def flow(items: list[dict]) -> None:
    """Tiles joined by chunky rounded arrows, e.g. the pipeline datos -> reglas -> ... -> parrilla."""
    parts = []
    for k, it in enumerate(items):
        if k:
            parts.append(icon("arrow_forward", "claro-arrow"))
        parts.append(tile_html(**it))
    st.html('<div class="claro-flow">' + "".join(parts) + "</div>")


def banner(text: str, icon_name: str = "pending_actions") -> None:
    st.html(f'<div class="claro-banner">{icon(icon_name)}<span>{escape(text)}</span></div>')


def coming_soon(phase: int, what: list[str], icon_name: str = "construction") -> None:
    """Placeholder body for pages that are built in a later phase."""
    section_label("En construcción")
    c1, c2 = st.columns([1, 4], vertical_alignment="center")
    with c1:
        tile(icon_name, f"Fase {phase}")
    with c2:
        st.markdown("Esta página se construye en la **fase %d**. Incluirá:" % phase)
        st.markdown("\n".join(f"- {w}" for w in what))
