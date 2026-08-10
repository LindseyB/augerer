from pathlib import Path

import pytest

import app as tarot_app
import readings


@pytest.fixture()
def client():
    tarot_app.app.config.update(TESTING=True)
    with tarot_app.app.test_client() as test_client:
        yield test_client


def test_index_page_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.data
    assert b"Aether" in body
    assert b"Single Card" in body
    assert b"Triad Spread" in body
    assert b"Arcana Library" in body


def test_index_page_has_no_redundant_draw_tile(client):
    response = client.get("/")
    body = response.data
    assert b'id="drawButton"' not in body


def test_library_page_uses_vanilla_lazyload_contract(client):
    response = client.get("/library")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert 'class="lazy"' in body
    assert 'data-src="' in body
    assert '<noscript>' in body
    assert 'card-image' in body

    library_script = Path(tarot_app.app.root_path) / 'static' / 'js' / 'library.js'
    script_contents = library_script.read_text(encoding='utf-8')
    assert 'window.LazyLoad' in script_contents
    assert 'elements_selector' in script_contents


def test_draw_api_returns_card_and_orientation(client):
    response = client.get("/api/draw")
    assert response.status_code == 200

    payload = response.get_json()
    assert payload is not None
    assert payload["orientation"] in {"upright", "reversed"}
    assert payload["card"]["name"]
    assert payload["card"]["slug"]


def test_debug_cards_page_lists_all_cards(client):
    response = client.get("/debug/cards")
    assert response.status_code == 200
    body = response.data
    assert b"Card &amp; SVG Match Check" in body
    assert str(len(tarot_app.CARDS)).encode() in body
    assert b"imported" in body
    assert b"generated" in body


def test_lookup_api_returns_slugged_results(client):
    response = client.get("/api/lookup?q=fool")
    assert response.status_code == 200

    payload = response.get_json()
    assert payload is not None
    assert payload["results"]
    assert {"name", "slug"}.issubset(payload["results"][0].keys())


def test_card_detail_route_renders_selected_card(client):
    card = tarot_app.CARDS[0]
    response = client.get(f"/card/{card['slug']}?orientation=reversed")

    assert response.status_code == 200
    assert card["name"].encode("utf-8") in response.data
    assert b"card-detail-layout" in response.data
    assert b"reversed" in response.data


def test_home_draw_control_has_no_orientation_selector(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"orientationSelect" not in response.data


def test_card_image_endpoint_uses_reversed_meaning_when_reversed(client):
    response = client.get("/card-image/the-fool.svg?orientation=reversed")
    assert response.status_code == 200
    assert response.mimetype == "image/svg+xml"
    assert b"Recklessness" in response.data


def test_card_detail_shows_zodiac_symbol_for_signed_cards(client):
    signed_card = next(card for card in tarot_app.CARDS if card["sign"])
    sign_name = signed_card["sign"][0]
    symbol = tarot_app.ZODIAC_SYMBOLS[sign_name]

    response = client.get(f"/card/{signed_card['slug']}")
    assert response.status_code == 200
    assert sign_name.title().encode("utf-8") in response.data
    assert symbol.encode("utf-8") in response.data


def test_svg_exists_for_each_card():
    card_dir = Path(tarot_app.CARD_IMAGE_DIR)
    svg_files = list(card_dir.glob("*.svg"))
    assert len(svg_files) >= len(tarot_app.CARDS)

    for card in tarot_app.CARDS[:5]:
        assert (card_dir / f"{card['slug']}.svg").exists()


def test_sun_card_svg_uses_concept_motif_class():
    sun_card = next(card for card in tarot_app.CARDS if card["name"].lower() == "the sun")
    markup = tarot_app._svg_markup_for_card(sun_card, orientation="upright", prefer_imported=False)

    assert "motif-the-sun" in markup


def test_each_major_arcana_has_unique_motif_class():
    major_cards = [card for card in tarot_app.CARDS if card["suit"] == "major"]

    for card in major_cards:
        expected_class = f"motif-{card['slug']}"
        markup = tarot_app._svg_markup_for_card(card, orientation="upright", prefer_imported=False)
        assert expected_class in markup


def test_each_minor_arcana_has_unique_motif_class():
    minor_cards = [card for card in tarot_app.CARDS if card["suit"] != "major"]

    for card in minor_cards:
        expected_class = f"motif-{card['slug']}"
        markup = tarot_app._svg_markup_for_card(card, orientation="upright", prefer_imported=False)
        assert expected_class in markup


def test_untrusted_source_is_not_trusted():
    card = next(c for c in tarot_app.CARDS if c["slug"] == "wheel-of-fortune")
    # A verified source is always trusted regardless of its title.
    assert tarot_app._source_is_trusted(
        card, {"page_url": "https://example.com/anything", "verified": True}
    )
    # An unverified source whose title does not match the card is rejected.
    assert not tarot_app._source_is_trusted(
        card, {"page_url": "https://freesvg.org/queen-of-swords-tarot-card"}
    )


def test_imported_svg_uses_mode_tint_without_quote_box(client):
    response = client.get("/card-image/the-fool.svg?orientation=reversed&mode=light")
    assert response.status_code == 200
    assert b"augerer-theme-lines" in response.data
    assert b"stroke:#1f3552 !important" in response.data
    assert b'x="8%" y="88%"' not in response.data


def test_card_image_mode_changes_generated_palette():
    card = next(c for c in tarot_app.CARDS if c["slug"] == "wheel-of-fortune")
    light = tarot_app._svg_markup_for_card(
        card, orientation="upright", mode="light", prefer_imported=False
    )
    dark = tarot_app._svg_markup_for_card(
        card, orientation="upright", mode="dark", prefer_imported=False
    )
    assert "#4f3a7a" in light
    assert "#4f3a7a" not in dark


def test_flat_generated_svg_is_transparent_black():
    card = next(c for c in tarot_app.CARDS if c["slug"] == "wheel-of-fortune")
    markup = tarot_app._svg_markup_for_card(
        card, orientation="upright", flat=True, prefer_imported=False
    )
    assert "url(#bg)" not in markup
    assert "#000000" in markup


def test_flat_imported_svg_forces_black(client):
    response = client.get("/card-image/the-fool.svg?orientation=upright&flat=1")
    assert response.status_code == 200
    assert b"stroke:#000000 !important" in response.data
    assert b"fill:#000000 !important" in response.data


def test_flat_svg_uses_exact_color_param():
    card = next(c for c in tarot_app.CARDS if c["slug"] == "wheel-of-fortune")
    markup = tarot_app._svg_markup_for_card(
        card, flat=True, flat_color="#00a4d6", prefer_imported=False
    )
    assert "#00a4d6" in markup
    assert "#000000" not in markup


def test_flat_svg_ignores_invalid_color(client):
    response = client.get("/card-image/wheel-of-fortune.svg?flat=1&color=javascript")
    assert response.status_code == 200
    assert b"#000000" in response.data


def test_reading_one_page_draws_a_card(client):
    response = client.get("/reading/one")
    assert response.status_code == 200
    body = response.data
    assert b"The Reader" in body
    assert b'window.readingSpread' in body
    assert b'"one"' in body
    assert b"drawBtn" in body
    # A one-card draw has no positional labels.
    assert b"spread-position" not in body


def test_reading_three_page_uses_past_present_future(client):
    response = client.get("/reading/three")
    assert response.status_code == 200
    body = response.data
    assert b"Past" in body
    assert b"Present" in body
    assert b"Future" in body
    assert b'"three"' in body
    assert b"drawBtn" in body


def test_one_card_prompt_includes_card_and_cues():
    card = next(c for c in tarot_app.CARDS if c["slug"] == "the-fool")
    prompt = readings.build_one_card_prompt(card, "upright")
    assert card["name"] in prompt
    assert "Upright" in prompt
    # At least one upright meaning cue should appear.
    assert card["meanings"]["upright"][0] in prompt


def test_three_card_prompt_labels_positions():
    picks = tarot_app.CARDS[:3]
    drawn = [
        {"card": card, "orientation": "upright", "position": position}
        for card, position in zip(picks, readings.THREE_CARD_POSITIONS)
    ]
    prompt = readings.build_three_card_prompt(drawn)
    for position in readings.THREE_CARD_POSITIONS:
        assert f"Position: {position}" in prompt
    for card in picks:
        assert card["name"] in prompt


def test_stream_reading_rejects_invalid_spread(client):
    response = client.post("/stream-reading", json={"spread": "five", "cards": []})
    assert response.status_code == 400


def test_stream_reading_rejects_wrong_card_count(client):
    response = client.post(
        "/stream-reading",
        json={"spread": "three", "cards": [{"slug": tarot_app.CARDS[0]["slug"]}]},
    )
    assert response.status_code == 400


def test_stream_reading_rejects_unknown_card(client):
    response = client.post(
        "/stream-reading",
        json={"spread": "one", "cards": [{"slug": "not-a-real-card"}]},
    )
    assert response.status_code == 400


def test_stream_reading_streams_chunks(client, monkeypatch):
    monkeypatch.setattr(tarot_app, "has_ai_client", lambda: True)
    monkeypatch.setattr(
        tarot_app,
        "stream_one_card_reading",
        lambda card, orientation, question=None: iter(["The Fool ", "begins."]),
    )

    slug = tarot_app.CARDS[0]["slug"]
    response = client.post(
        "/stream-reading",
        json={"spread": "one", "cards": [{"slug": slug, "orientation": "upright"}]},
    )
    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    body = response.get_data(as_text=True)
    assert '"chunk": "The Fool "' in body
    assert '"chunk": "begins."' in body
    assert '"done": true' in body


def test_stream_reading_requires_ai_client(client, monkeypatch):
    monkeypatch.setattr(tarot_app, "has_ai_client", lambda: False)
    slug = tarot_app.CARDS[0]["slug"]
    response = client.post(
        "/stream-reading",
        json={"spread": "one", "cards": [{"slug": slug, "orientation": "upright"}]},
    )
    assert response.status_code == 503


# --- Prompt voice: witchy + concise -------------------------------------------------

def test_reading_system_prompt_has_witchy_voice():
    from prompt_templates import load_prompt_text

    system_text = load_prompt_text("reading_system.md").lower()
    assert "witch" in system_text


def test_one_card_prompt_asks_to_be_concise():
    template = readings.load_prompt_template("one_card_user.md")
    content = template.content.lower()
    assert "2 short paragraphs" in content


def test_three_card_prompt_asks_to_be_concise():
    template = readings.load_prompt_template("three_card_user.md")
    content = template.content.lower()
    assert "2-3 sentences" in content
    # Still keeps the past/present/future structure.
    for position in ("past", "present", "future"):
        assert position in content


# --- Library page -------------------------------------------------------------------

def test_library_page_loads(client):
    response = client.get("/library")
    assert response.status_code == 200
    body = response.data
    assert b"Arcana Library" in body
    assert b"card-grid" in body
    assert str(len(tarot_app.CARDS)).encode() not in body or b"card-grid-item" in body


def test_library_page_has_filter_buttons(client):
    response = client.get("/library")
    body = response.data
    assert b"Major Arcana" in body
    assert b"Minor Arcana" in body
    assert b'data-filter="all"' in body


# --- Spread API -------------------------------------------------------------------

def test_api_spread_returns_one_card(client):
    response = client.get("/api/spread?n=1")
    assert response.status_code == 200
    payload = response.get_json()
    assert len(payload["cards"]) == 1
    assert payload["cards"][0]["card"]["name"]
    assert payload["cards"][0]["orientation"] in {"upright", "reversed"}


def test_api_spread_returns_three_cards_with_positions(client):
    response = client.get("/api/spread?n=3")
    assert response.status_code == 200
    payload = response.get_json()
    assert len(payload["cards"]) == 3
    positions = {c["position"] for c in payload["cards"]}
    assert positions == {"Past", "Present", "Future"}


