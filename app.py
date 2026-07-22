from __future__ import annotations

import json
import logging
import random
import re
from collections.abc import Iterator
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    render_template,
    request,
    stream_with_context,
)

from readings import (
    THREE_CARD_POSITIONS,
    stream_one_card_reading,
    stream_three_card_reading,
)
from ai_service import has_ai_client

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "tarot.json"
CARD_IMAGE_DIR = BASE_DIR / "static" / "cards"
FREESVG_SOURCES_PATH = BASE_DIR / "data" / "freesvg_card_sources.json"
ZODIAC_SYMBOLS = {
    "aries": "♈",
    "taurus": "♉",
    "gemini": "♊",
    "cancer": "♋",
    "leo": "♌",
    "virgo": "♍",
    "libra": "♎",
    "scorpio": "♏",
    "sagittarius": "♐",
    "capricorn": "♑",
    "aquarius": "♒",
    "pisces": "♓",
}

app = Flask(__name__)
logger = logging.getLogger(__name__)

ROMAN_NUMERALS = ['0', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X',
                  'XI', 'XII', 'XIII', 'XIV', 'XV', 'XVI', 'XVII', 'XVIII', 'XIX', 'XX', 'XXI']
RANK_NAMES = {'1': 'Ace', 'ace': 'Ace', '11': 'Page', 'page': 'Page',
              '12': 'Knight', 'knight': 'Knight', '13': 'Queen', 'queen': 'Queen',
              '14': 'King', 'king': 'King'}


@app.template_filter('card_number')
def card_number_filter(card: dict) -> str:
    suit = str(card.get('suit', '')).lower()
    rank = card.get('rank', '')
    if suit == 'major':
        try:
            return ROMAN_NUMERALS[int(rank)]
        except (IndexError, ValueError, TypeError):
            return str(rank)
    rank_str = str(rank).lower()
    return RANK_NAMES.get(rank_str, str(rank).title())


def _load_freesvg_sources() -> dict[str, dict[str, str]]:
    if not FREESVG_SOURCES_PATH.exists():
        return {}
    try:
        payload = json.loads(FREESVG_SOURCES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _source_path_tokens(url: str) -> set[str]:
    path = urlparse(url).path.strip("/").lower().replace("-", " ")
    return {token for token in re.sub(r"[^a-z0-9 ]+", " ", path).split() if token}


def _card_name_tokens(card: dict[str, Any]) -> set[str]:
    name = str(card.get("name", "")).lower()
    tokens = {token for token in re.sub(r"[^a-z0-9 ]+", " ", name).split() if token}
    stop_words = {"the", "of", "and", "in", "on", "a"}
    return {token for token in tokens if token not in stop_words}


def _looks_like_valid_source(card: dict[str, Any], source_url: str) -> bool:
    tokens = _source_path_tokens(source_url)
    if not tokens:
        return False

    suit = str(card.get("suit", "")).lower()
    rank = str(card.get("rank", "")).lower()

    if suit != "major":
        rank_token = {
            "1": "ace",
            "2": "two",
            "3": "three",
            "4": "four",
            "5": "five",
            "6": "six",
            "7": "seven",
            "8": "eight",
            "9": "nine",
            "10": "ten",
        }.get(rank, rank)
        suit_aliases = {suit}
        if suit == "coins":
            suit_aliases.add("pentacles")
        if suit == "pentacles":
            suit_aliases.add("coins")

        has_rank = rank_token in tokens
        has_suit = any(alias in tokens for alias in suit_aliases)
        return has_rank and has_suit

    required = _card_name_tokens(card)
    # Common acceptable alias for wheel-of-fortune pages.
    if "fortune" in required:
        required.add("wheel")
    # Require meaningful token overlap for majors.
    overlap = len(required & tokens)
    return overlap >= 1


def _source_is_trusted(card: dict[str, Any], source: Any) -> bool:
    if not isinstance(source, dict):
        return False
    source_url = source.get("page_url", "")
    if not source_url:
        return False
    # User-verified sources bypass the heuristic title match.
    if source.get("verified"):
        return True
    return _looks_like_valid_source(card, source_url)


def _normalize_card(raw: dict[str, Any]) -> dict[str, Any]:
    sign = raw.get("sign")
    signs = sign if isinstance(sign, list) else []
    meanings = raw.get("meanings") if isinstance(raw.get("meanings"), dict) else {}
    upright = meanings.get("upright") if isinstance(meanings.get("upright"), list) else []
    reversed_meanings = meanings.get("reversed") if isinstance(meanings.get("reversed"), list) else []

    name = str(raw.get("name", "Unknown card"))

    return {
        "name": str(raw.get("name", "Unknown card")),
        "rank": raw.get("rank", ""),
        "suit": str(raw.get("suit", "")),
        "planet": raw.get("planet") or "",
        "element": raw.get("element") or "",
        "slug": _slugify(name),
        "sign": signs,
        "meanings": {
            "upright": [str(item) for item in upright],
            "reversed": [str(item) for item in reversed_meanings],
        },
    }


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return normalized.strip("-") or "card"


def _safe_hex_color(value: str) -> str | None:
    candidate = (value or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", candidate):
        return candidate.lower()
    if re.fullmatch(r"#[0-9a-fA-F]{3}", candidate):
        r, g, b = candidate[1], candidate[2], candidate[3]
        return f"#{r}{r}{g}{g}{b}{b}".lower()
    return None


def _svg_markup_for_card(
    card: dict[str, Any],
    orientation: str = "upright",
    prefer_imported: bool = True,
    mode: str = "dark",
    flat: bool = False,
    flat_color: str = "#000000",
) -> str:
    name = escape(card["name"])
    name_lower = card["name"].lower()
    suit = (card["suit"] or "unknown").lower()
    suit_title = escape((card["suit"] or "unknown").title())
    rank = escape(str(card["rank"]))
    element = escape((card["element"] or "mystery").title())

    if mode == "light":
        themes = {
            "cups": ("#e6f5fb", "#d2ebf5", "#225f79"),
            "swords": ("#ecf2ff", "#dde8fb", "#2a466f"),
            "wands": ("#f8ece0", "#f3dfcc", "#7a3e1f"),
            "pentacles": ("#edf7e9", "#dff0d9", "#2d5a33"),
            "coins": ("#edf7e9", "#dff0d9", "#2d5a33"),
            "major": ("#efeafd", "#e4daf9", "#4f3a7a"),
        }
    else:
        themes = {
            "cups":      ("#070d1a", "#1e1b4b", "#fbbf24"),
            "swords":    ("#070d1a", "#1e1b4b", "#fbbf24"),
            "wands":     ("#070d1a", "#1e1b4b", "#fbbf24"),
            "pentacles": ("#070d1a", "#1e1b4b", "#fbbf24"),
            "coins":     ("#070d1a", "#1e1b4b", "#fbbf24"),
            "major":     ("#020617", "#1e1b4b", "#fbbf24"),
        }
    color_a, color_b, accent = themes.get(suit, themes["major"])
    if flat:
        accent = flat_color

    def _major_motif(value: str) -> str:
        motifs = {
            "the fool": '<g class="motif-the-fool" stroke="{a}" stroke-width="6" fill="none"><path d="M256 640h256"/><path d="M360 620l24-46 24 46-24 46z"/><line x1="408" y1="620" x2="494" y2="572"/><circle cx="506" cy="566" r="12"/></g>',
            "the magician": '<g class="motif-the-magician" stroke="{a}" stroke-width="6" fill="none"><path d="M276 430c44-52 172-52 216 0"/><path d="M276 628c44 52 172 52 216 0"/><line x1="384" y1="366" x2="384" y2="692"/></g>',
            "the high priestess": '<g class="motif-the-high-priestess" stroke="{a}" stroke-width="6" fill="none"><rect x="294" y="402" width="66" height="244" rx="12"/><rect x="408" y="402" width="66" height="244" rx="12"/><circle cx="384" cy="528" r="46"/></g>',
            "the empress": '<g class="motif-the-empress" stroke="{a}" stroke-width="6" fill="none"><path d="M384 388l36 74 82 12-58 56 14 82-74-40-74 40 14-82-58-56 82-12z"/><circle cx="384" cy="528" r="18"/></g>',
            "the emperor": '<g class="motif-the-emperor" stroke="{a}" stroke-width="6" fill="none"><rect x="304" y="392" width="160" height="236" rx="10"/><path d="M304 392l80-46 80 46"/><line x1="304" y1="552" x2="464" y2="552"/></g>',
            "the hierophant": '<g class="motif-the-hierophant" stroke="{a}" stroke-width="6" fill="none"><line x1="384" y1="370" x2="384" y2="666"/><line x1="330" y1="430" x2="438" y2="430"/><line x1="330" y1="488" x2="438" y2="488"/><circle cx="332" cy="620" r="20"/><circle cx="436" cy="620" r="20"/></g>',
            "the lovers": '<g class="motif-the-lovers" stroke="{a}" stroke-width="6" fill="none"><circle cx="330" cy="536" r="62"/><circle cx="438" cy="536" r="62"/><path d="M384 448c26-28 78-14 78 26 0 38-35 58-78 94-43-36-78-56-78-94 0-40 52-54 78-26z"/></g>',
            "the chariot": '<g class="motif-the-chariot" stroke="{a}" stroke-width="6" fill="none"><rect x="296" y="420" width="176" height="120" rx="10"/><line x1="384" y1="420" x2="384" y2="356"/><circle cx="330" cy="606" r="34"/><circle cx="438" cy="606" r="34"/></g>',
            "strength": '<g class="motif-strength" stroke="{a}" stroke-width="6" fill="none"><path d="M324 572c0-40 28-68 60-68 34 0 60 30 60 68"/><path d="M308 624c22-28 42-42 76-42 34 0 54 14 76 42"/><path d="M352 462c18-26 46-26 64 0"/></g>',
            "the hermit": '<g class="motif-the-hermit" stroke="{a}" stroke-width="6" fill="none"><path d="M346 628c20-78 26-148 50-220"/><rect x="400" y="412" width="38" height="54" rx="8"/><line x1="419" y1="466" x2="419" y2="646"/></g>',
            "wheel of fortune": '<g class="motif-wheel-of-fortune" stroke="{a}" stroke-width="6" fill="none"><circle cx="384" cy="528" r="156"/><circle cx="384" cy="528" r="104"/><line x1="384" y1="372" x2="384" y2="684"/><line x1="228" y1="528" x2="540" y2="528"/><line x1="274" y1="418" x2="494" y2="638"/><line x1="274" y1="638" x2="494" y2="418"/></g>',
            "justice": '<g class="motif-justice" stroke="{a}" stroke-width="6" fill="none"><line x1="384" y1="386" x2="384" y2="664"/><line x1="288" y1="424" x2="480" y2="424"/><path d="M306 424l-44 80h88z"/><path d="M462 424l-44 80h88z"/></g>',
            "the hanged man": '<g class="motif-the-hanged-man" stroke="{a}" stroke-width="6" fill="none"><line x1="304" y1="368" x2="464" y2="368"/><line x1="384" y1="368" x2="384" y2="476"/><circle cx="384" cy="516" r="30"/><path d="M384 546v96M384 606l-52 48M384 606l52 48"/></g>',
            "death": '<g class="motif-death" stroke="{a}" stroke-width="6" fill="none"><circle cx="384" cy="484" r="62"/><circle cx="362" cy="474" r="9"/><circle cx="406" cy="474" r="9"/><path d="M354 520h60M332 624l52-58 52 58"/></g>',
            "temperance": '<g class="motif-temperance" stroke="{a}" stroke-width="6" fill="none"><path d="M316 432h54l-24 86h-30z"/><path d="M398 452h54l-24 86h-30z"/><path d="M346 518c24 18 38 24 52 20"/></g>',
            "the devil": '<g class="motif-the-devil" stroke="{a}" stroke-width="6" fill="none"><path d="M324 452c0-38 30-70 60-70s60 32 60 70"/><line x1="344" y1="414" x2="320" y2="378"/><line x1="424" y1="414" x2="448" y2="378"/><rect x="324" y="500" width="120" height="132" rx="14"/></g>',
            "the tower": '<g class="motif-the-tower" stroke="{a}" stroke-width="6" fill="none"><rect x="312" y="386" width="144" height="286" rx="10"/><path d="M332 386l34-36h36l34 36"/><path d="M296 430l-38-56M472 430l38-56"/><line x1="332" y1="564" x2="436" y2="564"/></g>',
            "the star": '<g class="motif-the-star" stroke="{a}" stroke-width="6" fill="none"><path d="M384 374l40 84 94 14-68 66 16 94-82-44-82 44 16-94-68-66 94-14z"/><circle cx="278" cy="612" r="24"/><circle cx="490" cy="612" r="24"/></g>',
            "the moon": '<g class="motif-the-moon" stroke="{a}" stroke-width="7" fill="none"><path d="M450 408a132 132 0 1 0 0 240 108 108 0 1 1 0-240z"/><path d="M296 648l44-64h88l44 64"/></g>',
            "the sun": '<g class="motif-the-sun" stroke="{a}" stroke-width="6" fill="none"><circle cx="384" cy="528" r="124"/><g><line x1="384" y1="336" x2="384" y2="388"/><line x1="384" y1="668" x2="384" y2="720"/><line x1="192" y1="528" x2="244" y2="528"/><line x1="524" y1="528" x2="576" y2="528"/><line x1="258" y1="402" x2="296" y2="440"/><line x1="472" y1="616" x2="510" y2="654"/><line x1="472" y1="440" x2="510" y2="402"/><line x1="258" y1="654" x2="296" y2="616"/></g></g>',
            "judgement": '<g class="motif-judgment" stroke="{a}" stroke-width="6" fill="none"><path d="M298 430h172l-50 84h-72z"/><line x1="384" y1="514" x2="384" y2="646"/><path d="M310 646h148"/><path d="M340 690h88"/></g>',
            "judgment": '<g class="motif-judgment" stroke="{a}" stroke-width="6" fill="none"><path d="M298 430h172l-50 84h-72z"/><line x1="384" y1="514" x2="384" y2="646"/><path d="M310 646h148"/><path d="M340 690h88"/></g>',
            "the world": '<g class="motif-the-world" stroke="{a}" stroke-width="6" fill="none"><ellipse cx="384" cy="528" rx="156" ry="188"/><path d="M228 528h312M384 340v376"/><circle cx="272" cy="412" r="16"/><circle cx="496" cy="412" r="16"/><circle cx="272" cy="644" r="16"/><circle cx="496" cy="644" r="16"/></g>',
        }

        markup = motifs.get(value)
        if markup:
            return markup.format(a=accent)

        return '<g class="motif-major" stroke="{a}" stroke-width="6" fill="none"><circle cx="384" cy="528" r="152"/><path d="M384 370v316M226 528h316"/></g>'.format(a=accent)

    def _minor_pips(card_data: dict[str, Any]) -> str:
        if card_data["suit"] == "major":
            return ""

        suit_name = str(card_data["suit"]).lower()
        rank_value = card_data["rank"]
        if isinstance(rank_value, int) and 1 <= rank_value <= 10:
            rank_key = str(rank_value)
        else:
            rank_key = str(rank_value).lower()

        layouts: dict[str, list[tuple[int, int]]] = {
            "1": [(384, 538)],
            "2": [(340, 474), (428, 602)],
            "3": [(384, 434), (334, 548), (434, 662)],
            "4": [(334, 458), (434, 458), (334, 620), (434, 620)],
            "5": [(334, 458), (434, 458), (384, 538), (334, 620), (434, 620)],
            "6": [(316, 440), (452, 440), (316, 538), (452, 538), (316, 636), (452, 636)],
            "7": [(316, 434), (452, 434), (316, 522), (452, 522), (384, 604), (316, 692), (452, 692)],
            "8": [(300, 430), (384, 430), (468, 430), (300, 534), (468, 534), (300, 638), (384, 638), (468, 638)],
            "9": [(300, 426), (384, 426), (468, 426), (300, 530), (384, 530), (468, 530), (300, 634), (384, 634), (468, 634)],
            "10": [(300, 410), (468, 410), (300, 486), (468, 486), (300, 562), (468, 562), (300, 638), (468, 638), (300, 714), (468, 714)],
            "ace": [(384, 538)],
            "page": [(338, 466), (430, 466), (384, 572), (338, 678), (430, 678)],
            "knight": [(316, 456), (452, 456), (338, 548), (430, 548), (360, 640), (408, 640), (384, 730)],
            "queen": [(300, 430), (384, 430), (468, 430), (338, 538), (430, 538), (300, 646), (384, 646), (468, 646), (384, 736)],
            "king": [(300, 408), (384, 408), (468, 408), (300, 492), (468, 492), (300, 576), (384, 576), (468, 576), (300, 660), (468, 660)],
        }

        positions = layouts.get(rank_key, layouts["6"])

        pip = {
            "cups": '<path d="M{cx} {cy}c0-17 16-20 16-38 0 18 16 21 16 38 0 12-8 21-16 21s-16-9-16-21z" fill="none" stroke="{a}" stroke-width="4"/>',
            "swords": '<g stroke="{a}" stroke-width="4" fill="none"><line x1="{cx}" y1="{y1}" x2="{cx}" y2="{y2}"/><path d="M{cx} {y1}l-8 10h16z"/><line x1="{x1}" y1="{cy}" x2="{x2}" y2="{cy}"/></g>',
            "wands": '<g stroke="{a}" stroke-width="6" fill="none" stroke-linecap="round"><line x1="{x1}" y1="{y2}" x2="{x2}" y2="{y1}"/><line x1="{cx}" y1="{cy}" x2="{x2}" y2="{y2}" stroke-width="2"/></g>',
            "pentacles": '<g stroke="{a}" stroke-width="4" fill="none"><circle cx="{cx}" cy="{cy}" r="20"/><path d="M{cx} {y1}L{x2} {y2}L{x1} {ym}L{x2} {ym}L{x1} {y2}Z"/></g>',
            "coins": '<g stroke="{a}" stroke-width="4" fill="none"><circle cx="{cx}" cy="{cy}" r="20"/><path d="M{cx} {y1}L{x2} {y2}L{x1} {ym}L{x2} {ym}L{x1} {y2}Z"/></g>',
        }
        pip_template = pip.get(suit_name, pip["pentacles"])

        ornament_map = {
            "ace": '<g class="ornament-ace" stroke="{a}" stroke-width="4" fill="none"><circle cx="384" cy="538" r="112"/><path d="M328 672h112"/></g>',
            "page": '<g class="ornament-page" stroke="{a}" stroke-width="4" fill="none"><path d="M324 758h120"/><path d="M332 736h104"/></g>',
            "knight": '<g class="ornament-knight" stroke="{a}" stroke-width="4" fill="none"><path d="M286 736h196"/><path d="M314 706h140"/></g>',
            "queen": '<g class="ornament-queen" stroke="{a}" stroke-width="4" fill="none"><path d="M324 760h120"/><path d="M344 384l40 30 40-30"/></g>',
            "king": '<g class="ornament-king" stroke="{a}" stroke-width="4" fill="none"><path d="M318 760h132"/><path d="M384 360v40M364 380h40"/></g>',
        }
        ornament = ornament_map.get(rank_key, '')

        rank_class = re.sub(r"[^a-z0-9]+", "-", rank_key)

        output: list[str] = [
            '<g class="motif-{slug} minor-{suit} rank-{rank}">'.format(
                slug=card_data["slug"],
                suit=suit_name,
                rank=rank_class,
            )
        ]
        for x, y in positions:
            output.append(
                pip_template.format(
                    a=accent,
                    x1=x - 20,
                    x2=x + 20,
                    y1=y - 24,
                    y2=y + 18,
                    ym=y - 8,
                    cx=x,
                    cy=y,
                )
            )
        if ornament:
            output.append(ornament.format(a=accent))
        output.append("</g>")
        return "".join(output)

    motif = _major_motif(name_lower) if suit == "major" else _minor_pips(card)
    preferred = "reversed" if orientation == "reversed" else "upright"
    fallback = "upright" if preferred == "reversed" else "reversed"
    quote = ""
    preferred_values = card["meanings"].get(preferred, [])
    fallback_values = card["meanings"].get(fallback, [])
    if preferred_values:
        quote = escape(preferred_values[0]).capitalize()
    elif fallback_values:
        quote = escape(fallback_values[0]).capitalize()

    imported_svg_path = CARD_IMAGE_DIR / f"{card['slug']}.svg"
    source = FREESVG_SOURCES.get(card["slug"], {})
    can_use_imported = _source_is_trusted(card, source)

    if prefer_imported and imported_svg_path.exists() and can_use_imported:
        raw = imported_svg_path.read_text(encoding="utf-8")
        if "<svg" in raw and "</svg>" in raw:
            line_color = flat_color if flat else ("#fbbf24" if mode == "dark" else "#1f3552")
            overlay = (
                '<g id="augerer-quote-overlay">'
                f'<text x="50%" y="93.2%" text-anchor="middle" font-family="DM Sans, Arial, sans-serif" '
                f'font-size="3.2%" fill="{line_color}" style="paint-order:stroke;stroke:rgba(0,0,0,0.35);stroke-width:0.6%;">{quote}</text>'
                "</g>"
            )
            style = (
                '<style id="augerer-theme-lines">'
                f'path,line,polyline,polygon,circle,ellipse,rect{{stroke:{line_color} !important;}}'
                f'[stroke]{{stroke:{line_color} !important;}}'
                + (
                    f'[fill]:not([fill="none"]){{fill:{flat_color} !important;}}'
                    f'path,polygon,circle,ellipse{{fill:{flat_color} !important;}}'
                    if flat
                    else ''
                )
                + '</style>'
            )
            return raw.replace("</svg>", style + overlay + "</svg>", 1)

    heading_color = "#f8fafc" if mode == "dark" else "#10243b"
    meta_color = "#94a3b8" if mode == "dark" else "#304765"
    quote_color = "#f0d78c" if mode == "dark" else "#1e3552"
    inner_panel = "rgba(2,6,23,0.45)" if mode == "dark" else "rgba(255,255,255,0.5)"
    inner_stroke = "rgba(251,191,36,0.22)" if mode == "dark" else "rgba(34,61,92,0.24)"

    if flat:
        return f"""<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"768\" height=\"1280\" viewBox=\"0 0 768 1280\" role=\"img\" aria-label=\"{name}\">\n  <text x=\"384\" y=\"144\" text-anchor=\"middle\" font-family=\"'JetBrains Mono', monospace\" font-size=\"26\" fill=\"{flat_color}\" letter-spacing=\"5\">AUGERER TAROT</text>\n  <text x=\"384\" y=\"214\" text-anchor=\"middle\" font-family=\"'Space Grotesk', sans-serif\" font-size=\"60\" fill=\"{flat_color}\" font-weight=\"700\">{name}</text>\n  <text x=\"384\" y=\"286\" text-anchor=\"middle\" font-family=\"'DM Sans', sans-serif\" font-size=\"29\" fill=\"{flat_color}\">{suit_title} • Rank {rank} • {element}</text>\n  {motif}\n  <text x=\"384\" y=\"1038\" text-anchor=\"middle\" font-family=\"'DM Sans', sans-serif\" font-size=\"28\" fill=\"{flat_color}\">{quote}</text>\n  <text x=\"384\" y=\"1120\" text-anchor=\"middle\" font-family=\"'JetBrains Mono', monospace\" font-size=\"24\" fill=\"{flat_color}\" letter-spacing=\"4\">{card['slug'].upper()}</text>\n</svg>\n"""

    return f"""<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"768\" height=\"1280\" viewBox=\"0 0 768 1280\" role=\"img\" aria-label=\"{name}\">\n  <defs>\n    <linearGradient id=\"bg\" x1=\"0\" y1=\"0\" x2=\"1\" y2=\"1\">\n      <stop offset=\"0%\" stop-color=\"{color_a}\"/>\n      <stop offset=\"100%\" stop-color=\"{color_b}\"/>\n    </linearGradient>\n    <radialGradient id=\"halo\" cx=\"50%\" cy=\"44%\" r=\"48%\">\n      <stop offset=\"0%\" stop-color=\"{accent}\" stop-opacity=\"0.36\"/>\n      <stop offset=\"100%\" stop-color=\"{accent}\" stop-opacity=\"0\"/>\n    </radialGradient>\n  </defs>\n  <rect x=\"16\" y=\"16\" width=\"736\" height=\"1248\" rx=\"28\" fill=\"url(#bg)\" stroke=\"{accent}\" stroke-width=\"4\"/>\n  <rect x=\"52\" y=\"52\" width=\"664\" height=\"1176\" rx=\"20\" fill=\"{inner_panel}\" stroke=\"{inner_stroke}\" stroke-width=\"2\"/>\n  <circle cx=\"384\" cy=\"528\" r=\"264\" fill=\"url(#halo)\"/>\n  <text x=\"384\" y=\"144\" text-anchor=\"middle\" font-family=\"'JetBrains Mono', monospace\" font-size=\"26\" fill=\"{accent}\" letter-spacing=\"5\">AUGERER TAROT</text>\n  <text x=\"384\" y=\"214\" text-anchor=\"middle\" font-family=\"'Space Grotesk', sans-serif\" font-size=\"60\" fill=\"{heading_color}\" font-weight=\"700\">{name}</text>\n  <text x=\"384\" y=\"286\" text-anchor=\"middle\" font-family=\"'DM Sans', sans-serif\" font-size=\"29\" fill=\"{meta_color}\">{suit_title} • Rank {rank} • {element}</text>\n  {motif}\n  <text x=\"384\" y=\"1038\" text-anchor=\"middle\" font-family=\"'DM Sans', sans-serif\" font-size=\"28\" fill=\"{quote_color}\">{quote}</text>\n  <text x=\"384\" y=\"1120\" text-anchor=\"middle\" font-family=\"'JetBrains Mono', monospace\" font-size=\"24\" fill=\"{accent}\" letter-spacing=\"4\">{card['slug'].upper()}</text>\n</svg>\n"""


def _ensure_card_svgs(cards: list[dict[str, Any]]) -> None:
    CARD_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    for card in cards:
        image_path = CARD_IMAGE_DIR / f"{card['slug']}.svg"
        if image_path.exists():
            continue
        image_path.write_text(_svg_markup_for_card(card, orientation="upright", prefer_imported=False), encoding="utf-8")


def _signs_with_symbols(signs: list[str]) -> list[dict[str, str]]:
    return [
        {
            "name": sign,
            "label": sign.title(),
            "symbol": ZODIAC_SYMBOLS.get(sign.lower(), ""),
        }
        for sign in signs
    ]


def _load_cards() -> list[dict[str, Any]]:
    with DATA_PATH.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)

    cards = payload.get("cards") if isinstance(payload, dict) else None
    if not isinstance(cards, list):
        raise RuntimeError("Invalid tarot data format. Expected a top-level cards array.")

    return [_normalize_card(card) for card in cards if isinstance(card, dict)]


CARDS = _load_cards()
CARD_BY_NAME = {card["name"].lower(): card for card in CARDS}
CARD_BY_SLUG = {card["slug"]: card for card in CARDS}
SORTED_NAMES = sorted(card["name"] for card in CARDS)
FREESVG_SOURCES = _load_freesvg_sources()
_ensure_card_svgs(CARDS)


def _orientation_from_request(value: str) -> str:
    if value in {"upright", "reversed"}:
        return value
    return random.choice(["upright", "reversed"])


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.get("/library")
def library() -> str:
    return render_template("library.html", cards=CARDS)


@app.get("/card/<slug>")
def card_detail(slug: str) -> str:
    card = CARD_BY_SLUG.get(slug)
    if not card:
        abort(404)

    orientation = request.args.get("orientation", "").strip().lower()
    if orientation not in {"", "upright", "reversed"}:
        orientation = ""

    card_index = next((i for i, c in enumerate(CARDS) if c["slug"] == slug), -1)
    prev_card = CARDS[card_index - 1] if card_index > 0 else None
    next_card = CARDS[card_index + 1] if card_index < len(CARDS) - 1 else None

    return render_template(
        "card_detail.html",
        card=card,
        orientation=orientation,
        signs=_signs_with_symbols(card.get("sign", [])),
        prev_card=prev_card,
        next_card=next_card,
    )


def _random_orientation() -> str:
    return random.choice(["upright", "reversed"])


def _draw_reading_cards(count: int) -> list[dict[str, Any]]:
    picks = random.sample(CARDS, count)
    positions: tuple[str | None, ...] = (
        THREE_CARD_POSITIONS if count == 3 else (None,) * count
    )
    return [
        {"card": card, "orientation": _random_orientation(), "position": position}
        for card, position in zip(picks, positions)
    ]


@app.get("/reading/one")
def reading_one() -> str:
    return render_template("reading.html", spread="one")


@app.get("/reading/three")
def reading_three() -> str:
    return render_template("reading.html", spread="three")


@app.get("/api/spread")
def api_spread():
    try:
        n = int(request.args.get("n", "1"))
    except ValueError:
        n = 1
    n = max(1, min(n, 3))

    picks = random.sample(CARDS, n)
    positions = list(THREE_CARD_POSITIONS) if n == 3 else [None] * n

    result = [
        {
            "card": card,
            "orientation": _random_orientation(),
            "position": position or "",
        }
        for card, position in zip(picks, positions)
    ]
    return jsonify({"cards": result})


@app.post("/stream-reading")
def stream_reading():
    data = request.get_json(silent=True) or {}
    spread = str(data.get("spread", "")).strip().lower()
    raw_cards = data.get("cards")
    question = str(data.get("question", "")).strip()[:500]

    if spread not in {"one", "three"}:
        return jsonify({"error": "Invalid spread"}), 400
    if not isinstance(raw_cards, list):
        return jsonify({"error": "Missing cards"}), 400

    expected = 1 if spread == "one" else 3
    if len(raw_cards) != expected:
        return jsonify({"error": f"Expected {expected} card(s)"}), 400

    drawn: list[dict[str, Any]] = []
    for index, item in enumerate(raw_cards):
        if not isinstance(item, dict):
            return jsonify({"error": "Invalid card entry"}), 400
        card = CARD_BY_SLUG.get(str(item.get("slug", "")))
        if not card:
            return jsonify({"error": "Unknown card"}), 400
        orientation = str(item.get("orientation", "upright")).lower()
        if orientation not in {"upright", "reversed"}:
            orientation = "upright"
        position = THREE_CARD_POSITIONS[index] if spread == "three" else None
        drawn.append({"card": card, "orientation": orientation, "position": position})

    if not has_ai_client():
        return jsonify({"error": "AI reading is not configured"}), 503

    if spread == "one":
        chunks = stream_one_card_reading(drawn[0]["card"], drawn[0]["orientation"], question=question or None)
    else:
        chunks = stream_three_card_reading(drawn, question=question or None)

    def generate() -> Iterator[str]:
        try:
            for chunk in chunks:
                if chunk:
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as exc:  # pragma: no cover - stream runtime errors
            logger.error("Error in stream_reading: %s", exc)
            yield f"data: {json.dumps({'error': 'Failed to stream reading'})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


def _card_art_info(card: dict[str, Any]) -> dict[str, Any]:
    imported_svg_path = CARD_IMAGE_DIR / f"{card['slug']}.svg"
    source = FREESVG_SOURCES.get(card["slug"], {})
    source_url = source.get("page_url", "") if isinstance(source, dict) else ""
    uses_imported = imported_svg_path.exists() and _source_is_trusted(card, source)
    return {
        "card": card,
        "art_type": "imported" if uses_imported else "generated",
        "source_url": source_url,
        "has_file": imported_svg_path.exists(),
    }


@app.get("/debug/cards")
def debug_cards() -> str:
    entries = sorted(
        (_card_art_info(card) for card in CARDS),
        key=lambda item: item["card"]["name"].lower(),
    )
    imported = sum(1 for entry in entries if entry["art_type"] == "imported")
    return render_template(
        "debug_cards.html",
        entries=entries,
        total=len(entries),
        imported=imported,
        generated=len(entries) - imported,
    )


@app.get("/card-image/<slug>.svg")
def card_image_svg(slug: str):
    card = CARD_BY_SLUG.get(slug)
    if not card:
        abort(404)

    orientation = request.args.get("orientation", "upright").strip().lower()
    if orientation not in {"upright", "reversed"}:
        orientation = "upright"

    mode = request.args.get("mode", "dark").strip().lower()
    if mode not in {"light", "dark"}:
        mode = "dark"

    flat = request.args.get("flat", "").strip() in {"1", "true", "yes"}
    flat_color = _safe_hex_color(request.args.get("color", "")) or "#000000"

    svg_markup = _svg_markup_for_card(
        card, orientation=orientation, mode=mode, flat=flat, flat_color=flat_color
    )
    return Response(svg_markup, mimetype="image/svg+xml")


@app.get("/api/draw")
def api_draw():
    orientation = _orientation_from_request(request.args.get("orientation", "random").lower())
    card = random.choice(CARDS)
    return jsonify({"card": card, "orientation": orientation})


@app.get("/api/lookup")
def api_lookup():
    query = request.args.get("q", "").strip().lower()
    if not query:
        return jsonify({"results": []})

    prefix_matches = [card for card in CARDS if card["name"].lower().startswith(query)]
    partial_matches = [
        card for card in CARDS if query in card["name"].lower() and card not in prefix_matches
    ]
    ranked = (prefix_matches + partial_matches)[:12]
    results = [{"name": card["name"], "slug": card["slug"]} for card in ranked]
    return jsonify({"results": results})


@app.get("/api/card")
def api_card():
    name = request.args.get("name", "").strip().lower()
    card = CARD_BY_NAME.get(name)
    if not card:
        return jsonify({"error": "Card not found"}), 404
    return jsonify({"card": card})


@app.get("/api/card/<slug>")
def api_card_by_slug(slug: str):
    card = CARD_BY_SLUG.get(slug)
    if not card:
        return jsonify({"error": "Card not found"}), 404
    return jsonify({"card": card})


if __name__ == "__main__":
    app.run(debug=True)
