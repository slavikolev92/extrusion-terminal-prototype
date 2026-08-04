import csv
import io
import re
from decimal import Decimal, localcontext
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app import db
from app.importer import IMPORT_FIELDS, import_cards_from_csv
from app.main import terminal_context
from app.pallet_summary import (
    PalletSummaryDataError,
    build_terminal_pallet_summary,
)


_AUTO_NET = object()


def create_released_test_card(
    db_path: Path,
    *,
    order_number: str,
    machine_id: int,
) -> int:
    assert db.DB_PATH == db_path
    row = {
        "order_number": order_number,
        "customer": f"Pallet summary customer {order_number}",
        "product_type": "ТСФ 890/0.082",
        "ordered_gross_kg": "500",
        "ordered_rolls": "5",
        "product_form": "плоско",
        "material": "LDPE",
        "size_thickness": "890 / 0.082",
        "notes": "Pallet summary test card.",
        "extrusion_sequence": "1",
        "extrusion_folding": "single",
        "extrusion_next_operation": "rewind",
        "extrusion_treatment": "corona",
        "raw_material_a": "LDPE; A | 50%",
        "raw_material_b": "LLDPE; B | 30%",
        "raw_material_c": "MDPE; HDPE C | 5%",
        "linear_pe": "LLDPE; Линеен PE | 8%",
        "antistatic": "Antistatic; Антистатик 1% | 1%",
        "masterbatch": "Masterbatch; Бял мастербач | 4%",
        "chalk": "Filler; Креда 5% | 2%",
        "packaging_method": "rolls",
    }
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=IMPORT_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerow({field: row.get(field, "") for field in IMPORT_FIELDS})
    result = import_cards_from_csv(
        f"{order_number}.csv",
        output.getvalue().encode("utf-8"),
        overwrite_existing=False,
    )
    assert result.rows_imported == 1
    with db.connect() as connection:
        card_id = int(
            connection.execute(
                "SELECT id FROM cards WHERE order_number = ?",
                (order_number,),
            ).fetchone()["id"]
        )
    assert db.release_card(
        card_id,
        machine_id,
        1,
        db.fetch_admin_card_detail(card_id)["version"],
    ).ok
    return card_id


def start_test_shift() -> None:
    configuration = db.fetch_terminal_configuration()
    assert db.start_shift("1", int(configuration["version"])).ok


def add_entered_roll(
    card_id: int,
    *,
    gross_weight: str,
    tare_weight: str,
    pallet: int,
) -> None:
    card = db.fetch_terminal_card_detail(card_id)
    assert card is not None
    assert db.start_production_timing(card_id, int(card["version"])).ok
    card = db.fetch_terminal_card_detail(card_id)
    assert card is not None
    assert db.add_roll_gross_weight(
        card_id,
        int(card["version"]),
        gross_weight,
        tare_weight,
        str(pallet),
    ).ok


def render_terminal_card(card_id: int) -> str:
    env = Environment(
        loader=FileSystemLoader("app/templates"),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["url_for"] = (
        lambda name, **kwargs: f"/static{kwargs.get('path', '')}"
    )
    return env.get_template("terminal.html").render(
        **terminal_context(selected_card_id=card_id),
    )


def card_version(card_id: int) -> int:
    card = db.fetch_terminal_card_detail(card_id)
    assert card is not None
    return int(card["version"])


def start_card(card_id: int) -> None:
    assert db.start_production_timing(card_id, card_version(card_id)).ok


def add_saved_roll(
    card_id: int,
    *,
    gross_weight: str,
    tare_weight: str,
    pallet_number: str,
) -> None:
    assert db.add_roll_gross_weight(
        card_id,
        card_version(card_id),
        gross_weight,
        tare_weight,
        pallet_number,
    ).ok


def pallet_modal_block(html: str) -> str:
    start = html.find('<div class="pallet-summary-overlay"')
    assert start != -1
    following_hosts = [
        position
        for marker in (
            '<div class="rewinding-overlay"',
            '<div class="roll-change-overlay"',
            '<div class="finish-confirm-modal"',
            "<script",
        )
        if (position := html.find(marker, start + 1)) != -1
    ]
    assert following_hosts
    return html[start:min(following_hosts)]


def rendered_cell_texts(block: str, tag: str, scope: str | None = None) -> list[str]:
    scope_pattern = rf'\s+scope="{scope}"' if scope else ""
    return [
        re.sub(r"<[^>]+>", "", value).strip()
        for value in re.findall(
            rf"<{tag}{scope_pattern}[^>]*>(.*?)</{tag}>",
            block,
            flags=re.S,
        )
    ]


def javascript_function_source(html: str, declaration: str) -> str:
    start = html.find(declaration)
    assert start != -1, f"missing JavaScript function: {declaration}"
    end = html.find("\n      };", start)
    assert end != -1, f"unterminated JavaScript function: {declaration}"
    return html[start:end]


def test_terminal_context_attaches_ready_pallet_summary_from_fetched_rolls(
    temp_db_path: Path,
):
    card_id = create_released_test_card(
        temp_db_path,
        order_number="PALLET-SUMMARY-READY",
        machine_id=1,
    )
    start_test_shift()
    add_entered_roll(card_id, gross_weight="10.50", tare_weight="0.30", pallet=7)

    context = terminal_context(selected_machine_id=1, selected_card_id=card_id)

    assert context["selected_card"]["pallet_summary"] == {
        "state": "ready",
        "rows": [{
            "pallet_number": 7,
            "pallet_label": "7",
            "roll_count": 1,
            "gross_weight": Decimal("10.5"),
            "net_weight": Decimal("10.2"),
            "gross_display": "10.5",
            "net_display": "10.2",
        }],
        "total": {
            "roll_count": 1,
            "gross_weight": Decimal("10.5"),
            "net_weight": Decimal("10.2"),
            "gross_display": "10.5",
            "net_display": "10.2",
        },
    }


def test_terminal_context_attaches_empty_pallet_summary_for_no_rolls(
    temp_db_path: Path,
):
    card_id = create_released_test_card(
        temp_db_path,
        order_number="PALLET-SUMMARY-EMPTY",
        machine_id=1,
    )

    context = terminal_context(selected_machine_id=1, selected_card_id=card_id)

    assert context["selected_card"]["pallet_summary"] == {
        "state": "empty",
        "rows": [],
        "total": None,
    }


def test_terminal_context_builds_only_the_selected_card_summary(
    temp_db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    card_id = create_released_test_card(
        temp_db_path,
        order_number="PALLET-SUMMARY-SELECTED",
        machine_id=1,
    )
    other_card_id = create_released_test_card(
        temp_db_path,
        order_number="PALLET-SUMMARY-OTHER",
        machine_id=2,
    )
    start_test_shift()
    add_entered_roll(card_id, gross_weight="10.50", tare_weight="0.30", pallet=7)
    add_entered_roll(other_card_id, gross_weight="99.00", tare_weight="0.30", pallet=9)

    calls: list[object] = []
    real_builder = build_terminal_pallet_summary

    def spy(roll_entries: object) -> dict[str, object]:
        calls.append(roll_entries)
        return real_builder(roll_entries)

    monkeypatch.setattr("app.main.build_terminal_pallet_summary", spy)

    context = terminal_context(selected_machine_id=1, selected_card_id=card_id)

    assert len(calls) == 1
    assert calls[0] is context["selected_card"]["roll_entries"]
    assert (
        context["selected_card"]["pallet_summary"]["total"]["gross_weight"]
        == Decimal("10.5")
    )


def test_terminal_context_contains_summary_failure_and_logs_card_id_only(
    temp_db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    card_id = create_released_test_card(
        temp_db_path,
        order_number="PALLET-SUMMARY-ERROR",
        machine_id=1,
    )

    def explode(_roll_entries: object) -> dict[str, object]:
        secret_value = "secret-" + "order-content"
        raise RuntimeError(secret_value)

    monkeypatch.setattr("app.main.build_terminal_pallet_summary", explode)

    with caplog.at_level("ERROR", logger="app.main"):
        context = terminal_context(selected_machine_id=1, selected_card_id=card_id)

    assert context["selected_card"]["pallet_summary"] == {
        "state": "error",
        "rows": [],
        "total": None,
    }
    record = next(
        record for record in caplog.records
        if "Terminal pallet summary failed" in record.getMessage()
    )
    assert f"card_id={card_id}" in record.getMessage()
    assert "secret-order-content" not in record.getMessage()
    assert "exception_type=RuntimeError" in record.getMessage()


@pytest.mark.parametrize(
    ("status", "marked_for_rewinding"),
    [
        ("pending", False),
        ("running", True),
        ("paused", True),
        ("awaiting_rewinding", True),
        ("completed", False),
    ],
)
def test_terminal_render_shows_one_pallet_button_in_heading_actions_for_every_status(
    temp_db_path: Path,
    status: str,
    marked_for_rewinding: bool,
):
    card_id = create_released_test_card(
        temp_db_path,
        order_number=f"PALLET-BUTTON-{status.upper()}",
        machine_id=1,
    )
    if status != "pending":
        start_test_shift()
        start_card(card_id)
    if marked_for_rewinding:
        assert db.update_rewinding_roll_count(
            card_id,
            card_version(card_id),
            3,
        ).ok
    if status == "paused":
        assert db.pause_production_timing(card_id, card_version(card_id)).ok
    elif status == "awaiting_rewinding":
        assert db.finish_card(card_id, card_version(card_id)).ok
    elif status == "completed":
        add_saved_roll(
            card_id,
            gross_weight="10.50",
            tare_weight="0.30",
            pallet_number="1",
        )
        assert db.finish_card(card_id, card_version(card_id)).ok

    html = render_terminal_card(card_id)

    assert len(re.findall(r"<button[^>]+data-pallet-summary-open", html)) == 1
    button = re.search(
        r"<button[^>]+data-pallet-summary-open[^>]*>(.*?)</button>",
        html,
        flags=re.S,
    )
    assert button
    assert re.sub(r"<[^>]+>", "", button.group(1)).strip() == "Палети"
    actions_match = re.search(
        r'<div class="roll-secondary-actions"[^>]*data-roll-secondary-actions[^>]*>'
        r"(.*?)</div>",
        html,
        flags=re.S,
    )
    assert actions_match
    actions = re.sub(r"<[^>]+>", " ", actions_match.group(1))
    assert "Палети" in actions
    if marked_for_rewinding:
        assert actions.index("Пренавиване") < actions.index("Палети")
    else:
        assert "Пренавиване" not in actions


def test_terminal_render_ready_modal_has_semantic_ordered_summary_table(
    temp_db_path: Path,
):
    card_id = create_released_test_card(
        temp_db_path,
        order_number="PALLET-MODAL-READY",
        machine_id=1,
    )
    start_test_shift()
    start_card(card_id)
    add_saved_roll(
        card_id,
        gross_weight="10.00",
        tare_weight="0.30",
        pallet_number="10",
    )
    add_saved_roll(
        card_id,
        gross_weight="2.00",
        tare_weight="0.30",
        pallet_number="",
    )
    add_saved_roll(
        card_id,
        gross_weight="3.50",
        tare_weight="0.30",
        pallet_number="2",
    )

    modal = pallet_modal_block(render_terminal_card(card_id))

    assert "Обобщение по палети" in modal
    assert "Поръчка №PALLET-MODAL-READY" in modal
    thead = re.search(r"<thead>(.*?)</thead>", modal, flags=re.S)
    tbody = re.search(r"<tbody>(.*?)</tbody>", modal, flags=re.S)
    tfoot = re.search(r"<tfoot>(.*?)</tfoot>", modal, flags=re.S)
    assert thead and tbody and tfoot
    assert rendered_cell_texts(thead.group(1), "th", "col") == [
        "Палет",
        "Брой ролки",
        "Бруто, кг",
        "Нето, кг",
    ]
    assert rendered_cell_texts(tbody.group(1), "th", "row") == [
        "2",
        "10",
        "Без палет",
    ]
    assert rendered_cell_texts(tbody.group(1), "td") == [
        "1", "3.5", "3.2",
        "1", "10.0", "9.7",
        "1", "2.0", "1.7",
    ]
    assert 'class="pallet-summary-total"' in tfoot.group(1)
    assert "data-pallet-summary-total" in tfoot.group(1)
    assert rendered_cell_texts(tfoot.group(1), "th", "row") == ["Общо"]
    assert rendered_cell_texts(tfoot.group(1), "td") == [
        "3", "15.5", "14.6",
    ]


def test_terminal_render_empty_modal_explains_that_no_rolls_are_entered(
    temp_db_path: Path,
):
    card_id = create_released_test_card(
        temp_db_path,
        order_number="PALLET-MODAL-EMPTY",
        machine_id=1,
    )

    html = render_terminal_card(card_id)

    assert "Няма въведени ролки." in html
    assert "data-pallet-summary-empty" in html


def test_terminal_render_error_modal_keeps_selected_card_visible(
    temp_db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    card_id = create_released_test_card(
        temp_db_path,
        order_number="PALLET-MODAL-ERROR",
        machine_id=1,
    )

    def explode(_roll_entries: object) -> dict[str, object]:
        raise RuntimeError("bad saved roll")

    monkeypatch.setattr("app.main.build_terminal_pallet_summary", explode)

    html = render_terminal_card(card_id)

    assert "PALLET-MODAL-ERROR" in html
    assert "Pallet summary customer PALLET-MODAL-ERROR" in html
    assert "data-pallet-summary-error" in html
    assert (
        "Обобщението по палети не може да бъде показано. "
        "Проверете данните за ролките."
    ) in html


def test_terminal_render_modal_is_read_only_and_ignores_future_pallet_default(
    temp_db_path: Path,
):
    card_id = create_released_test_card(
        temp_db_path,
        order_number="PALLET-MODAL-READ-ONLY",
        machine_id=1,
    )
    start_test_shift()
    start_card(card_id)
    assert db.update_current_pallet_number(
        card_id,
        card_version(card_id),
        "77",
    ).ok
    add_saved_roll(
        card_id,
        gross_weight="8.00",
        tare_weight="0.30",
        pallet_number="",
    )

    modal = pallet_modal_block(render_terminal_card(card_id))

    for forbidden_tag in ("form", "input", "select", "textarea", "a"):
        assert not re.search(rf"<{forbidden_tag}(?:\s|>)", modal)
    assert "type=\"submit\"" not in modal
    assert "action=" not in modal
    assert "/terminal/cards/" not in modal
    buttons = re.findall(r"<button([^>]*)>(.*?)</button>", modal, flags=re.S)
    assert len(buttons) == 1
    button_attributes, button_body = buttons[0]
    assert 'type="button"' in button_attributes
    assert "data-pallet-summary-close" in button_attributes
    assert re.sub(r"<[^>]+>", "", button_body).strip() == "Затвори"
    assert rendered_cell_texts(modal, "th", "row") == ["Без палет", "Общо"]
    assert not re.search(r">\s*77\s*<", modal)


def test_terminal_render_pallet_summary_coordinator_owns_one_hook_set_and_keyboard_path(
    temp_db_path: Path,
):
    card_id = create_released_test_card(
        temp_db_path,
        order_number="PALLET-COORDINATOR-HOOKS",
        machine_id=1,
    )

    html = render_terminal_card(card_id)

    for hook in (
        "data-pallet-summary-open",
        "data-pallet-summary-overlay",
        "data-pallet-summary-dialog",
        "data-pallet-summary-close",
        "terminal-refresh-alert-button",
    ):
        assert hook in html
    assert len(re.findall(r"<button[^>]+data-pallet-summary-open", html)) == 1
    assert len(re.findall(r"<div[^>]+data-pallet-summary-overlay", html)) == 1
    assert html.count('const palletSummaryOverlay = document.querySelector(') == 1
    assert html.count('document.addEventListener("keydown",') == 3
    assert "setDrawerBackgroundIsolated(true, \"pallet-summary\");" in html
    assert "trapModalFocus(event, palletSummaryDialog);" in html


def test_terminal_render_pallet_summary_coordinator_makes_surfaces_mutually_exclusive(
    temp_db_path: Path,
):
    card_id = create_released_test_card(
        temp_db_path,
        order_number="PALLET-COORDINATOR-SURFACES",
        machine_id=1,
    )

    html = render_terminal_card(card_id)
    pallet_open = javascript_function_source(
        html,
        "const openPalletSummary = (trigger) => {",
    )
    for close_call in (
        "closeQueue(false);",
        "closeWaiting(false);",
        "closeHistory(false);",
        "closeRewinding(false);",
    ):
        assert close_call in pallet_open
        assert pallet_open.index(close_call) < pallet_open.index(
            "palletSummaryOverlay.hidden = false;"
        )

    for declaration in (
        "const openQueue = () => {",
        "const openWaiting = () => {",
        "const openHistory = () => {",
        "const openRewinding = () => {",
    ):
        opener = javascript_function_source(html, declaration)
        assert "closePalletSummary(false);" in opener


def test_terminal_render_pallet_summary_correction_lock_closes_and_blocks_trigger(
    temp_db_path: Path,
):
    card_id = create_released_test_card(
        temp_db_path,
        order_number="PALLET-CORRECTION-LOCK",
        machine_id=1,
    )

    html = render_terminal_card(card_id)
    selector_start = html.index(
        "const correctionBlockedControls = document.querySelectorAll("
    )
    selector_end = html.index(");", selector_start)
    correction_selector = html[selector_start:selector_end]
    assert "[data-pallet-summary-open]" in correction_selector

    row_edit = javascript_function_source(html, "const openRowEdit = (row, focusError = false) => {")
    assert "closePalletSummary(false);" in row_edit
    assert row_edit.index("closePalletSummary(false);") < row_edit.index("activeRow = row;")


def test_terminal_render_selected_card_stale_dispatch_follows_refresh_alert_once(
    temp_db_path: Path,
):
    card_id = create_released_test_card(
        temp_db_path,
        order_number="PALLET-CARD-STALE",
        machine_id=1,
    )

    html = render_terminal_card(card_id)
    poll_start = html.index("const pollSnapshot = async () => {")
    poll_end = html.index("window.setInterval(pollSnapshot, 10000);", poll_start)
    poll_source = html[poll_start:poll_end]
    card_stale_dispatch = (
        'document.dispatchEvent(new CustomEvent("terminal:card-stale"));'
    )

    assert html.count(card_stale_dispatch) == 1
    assert html.count('document.addEventListener("terminal:card-stale",') == 1
    assert poll_source.count(card_stale_dispatch) == 1
    assert poll_source.index("if (snapshot.signature === currentSignature)") < (
        poll_source.index(card_stale_dispatch)
    )
    assert poll_source.index("showRefreshAlert();") < poll_source.index(
        card_stale_dispatch
    )
    assert html.count(
        'document.dispatchEvent(new CustomEvent("terminal:shift-stale"));'
    ) == 1
    assert html.count('document.addEventListener("terminal:shift-stale",') == 2


def test_terminal_render_shift_stale_coordinator_closes_in_capture_before_takeover(
    temp_db_path: Path,
):
    card_id = create_released_test_card(
        temp_db_path,
        order_number="PALLET-SHIFT-STALE-ORDER",
        machine_id=1,
    )

    html = render_terminal_card(card_id)

    existing_takeover = re.search(
        r'document\.addEventListener\("terminal:shift-stale", \(\) => \{'
        r'.*?shiftWindow\.dataset\.shiftBlocking = "true";'
        r'.*?\n      \}\);',
        html,
        flags=re.S,
    )
    coordinator_capture = re.search(
        r'document\.addEventListener\("terminal:shift-stale", \(\) => \{'
        r'\s+closePalletSummary\(false\);'
        r'\s+\}, \{ capture: true \}\);',
        html,
    )

    assert existing_takeover
    assert coordinator_capture


def test_terminal_render_pallet_summary_stale_takeover_closes_without_stale_focus(
    temp_db_path: Path,
):
    card_id = create_released_test_card(
        temp_db_path,
        order_number="PALLET-STALE-TAKEOVER",
        machine_id=1,
    )

    html = render_terminal_card(card_id)
    card_listener_start = html.index(
        'document.addEventListener("terminal:card-stale",'
    )
    card_listener_end = html.index("\n      });", card_listener_start)
    card_listener = html[card_listener_start:card_listener_end]
    shift_listener_start = html.rindex(
        'document.addEventListener("terminal:shift-stale",'
    )
    shift_listener_end = html.index("\n      });", shift_listener_start)
    shift_listener = html[shift_listener_start:shift_listener_end]

    assert "closePalletSummary(false);" in card_listener
    assert 'document.getElementById("terminal-refresh-alert-button")?.focus();' in (
        card_listener
    )
    assert "closePalletSummary(true);" not in card_listener
    assert "palletSummaryReturnFocus" not in card_listener
    assert "closePalletSummary(false);" in shift_listener


def roll(
    gross: object,
    tare: object = "0.30",
    net: object = _AUTO_NET,
    pallet: object = None,
) -> dict[str, object]:
    if net is _AUTO_NET and gross is None:
        calculated_net = None
    elif net is _AUTO_NET:
        calculated_net = Decimal(str(gross)) - Decimal(str(tare))
    else:
        calculated_net = net
    return {
        "gross_weight": gross,
        "tare_weight": tare,
        "net_weight": calculated_net,
        "pallet_number": pallet,
    }


def test_pallet_summary_is_empty_when_no_gross_roll_is_entered():
    summary = build_terminal_pallet_summary([roll(None), roll(None)])

    assert summary == {"state": "empty", "rows": [], "total": None}


def test_pallet_summary_groups_one_numbered_pallet_and_builds_total():
    summary = build_terminal_pallet_summary([
        roll("10.50", "0.30", pallet=7),
        roll("11.20", "0.30", pallet=7),
    ])

    assert summary == {
        "state": "ready",
        "rows": [{
            "pallet_number": 7,
            "pallet_label": "7",
            "roll_count": 2,
            "gross_weight": Decimal("21.70"),
            "net_weight": Decimal("21.10"),
            "gross_display": "21.7",
            "net_display": "21.1",
        }],
        "total": {
            "roll_count": 2,
            "gross_weight": Decimal("21.70"),
            "net_weight": Decimal("21.10"),
            "gross_display": "21.7",
            "net_display": "21.1",
        },
    }


def test_pallet_summary_sorts_numbered_pallets_numerically_with_gaps():
    summary = build_terminal_pallet_summary([
        roll("5.00", "0.00", pallet=10),
        roll("3.00", "0.00", pallet=2),
    ])

    assert [row["pallet_label"] for row in summary["rows"]] == ["2", "10"]
    assert [row["gross_weight"] for row in summary["rows"]] == [
        Decimal("3.00"),
        Decimal("5.00"),
    ]


def test_pallet_summary_keeps_all_unassigned_rolls_under_without_pallet():
    summary = build_terminal_pallet_summary([
        roll("5.00", "0.30"),
        roll("7.00", "0.30"),
    ])

    assert summary["rows"] == [{
        "pallet_number": None,
        "pallet_label": "Без палет",
        "roll_count": 2,
        "gross_weight": Decimal("12.00"),
        "net_weight": Decimal("11.40"),
        "gross_display": "12.0",
        "net_display": "11.4",
    }]
    assert summary["total"]["roll_count"] == 2


def test_pallet_summary_places_mixed_unassigned_rolls_last():
    summary = build_terminal_pallet_summary([
        roll("10.00", "0.30", pallet=10),
        roll("2.00", "0.30", pallet=None),
        roll("3.00", "0.30", pallet=2),
        roll("4.00", "0.30", pallet=None),
    ])

    assert [row["pallet_label"] for row in summary["rows"]] == [
        "2", "10", "Без палет",
    ]
    assert [row["roll_count"] for row in summary["rows"]] == [1, 1, 2]
    assert [row["gross_weight"] for row in summary["rows"]] == [
        Decimal("3.00"),
        Decimal("10.00"),
        Decimal("6.00"),
    ]
    assert [row["net_weight"] for row in summary["rows"]] == [
        Decimal("2.70"),
        Decimal("9.70"),
        Decimal("5.40"),
    ]
    assert summary["total"]["roll_count"] == 4


def test_pallet_summary_uses_saved_rolls_not_a_current_pallet_default():
    saved_roll = roll("10.00", "0.30", pallet=None)
    saved_roll["current_pallet_number"] = 7

    summary = build_terminal_pallet_summary([saved_roll])

    assert summary["rows"][0]["pallet_number"] is None
    assert summary["rows"][0]["pallet_label"] == "Без палет"


def test_pallet_summary_accepts_a_zero_weight_entered_roll():
    summary = build_terminal_pallet_summary([roll("0.00", "0.00", pallet=1)])

    assert summary["state"] == "ready"
    assert summary["rows"][0]["roll_count"] == 1
    assert summary["rows"][0]["gross_weight"] == Decimal("0.00")
    assert summary["rows"][0]["net_weight"] == Decimal("0.00")


def test_pallet_summary_sums_exact_values_before_one_final_rounding():
    summary = build_terminal_pallet_summary([
        roll("10.04", "0.00", pallet=1),
        roll("10.04", "0.00", pallet=1),
    ])

    assert summary["rows"][0]["gross_weight"] == Decimal("20.08")
    assert summary["rows"][0]["gross_display"] == "20.1"
    assert summary["total"]["gross_display"] == "20.1"


def test_pallet_summary_uses_decimal_half_up_at_the_display_boundary():
    summary = build_terminal_pallet_summary([
        roll("0.05", "0.00", pallet=1),
    ])

    assert summary["rows"][0]["gross_display"] == "0.1"


def test_pallet_summary_large_exact_values_ignore_caller_decimal_context():
    exact_weight = Decimal("123456789012345678901234567.45")
    entry = {
        "gross_weight": exact_weight,
        "tare_weight": Decimal("0"),
        "net_weight": exact_weight,
        "pallet_number": 1,
    }

    with localcontext() as context:
        context.prec = 6
        summary = build_terminal_pallet_summary([entry])

    row = summary["rows"][0]
    assert row["gross_weight"] == exact_weight
    assert row["net_weight"] == exact_weight
    assert row["gross_display"] == "123456789012345678901234567.5"
    assert row["net_display"] == "123456789012345678901234567.5"
    assert summary["total"]["gross_weight"] == exact_weight
    assert summary["total"]["net_weight"] == exact_weight
    assert summary["total"]["gross_display"] == "123456789012345678901234567.5"
    assert summary["total"]["net_display"] == "123456789012345678901234567.5"


def test_pallet_summary_rejects_context_rounded_large_saved_net():
    entry = {
        "gross_weight": Decimal("123456789012345678901234567.45"),
        "tare_weight": Decimal("0"),
        "net_weight": Decimal("123456789012345678901234567.4"),
        "pallet_number": 1,
    }

    with localcontext() as context:
        context.prec = 28
        with pytest.raises(PalletSummaryDataError, match="net_weight"):
            build_terminal_pallet_summary([entry])


def test_pallet_summary_parses_float_weights_through_their_decimal_text():
    summary = build_terminal_pallet_summary([roll(10.1, 0.0, pallet=1)])

    assert summary["rows"][0]["gross_weight"] == Decimal("10.1")
    assert summary["rows"][0]["net_weight"] == Decimal("10.1")


@pytest.mark.parametrize(
    ("entry", "field_name"),
    [
        (roll("bad", "0.30", "1.00", 1), "gross_weight"),
        (roll("NaN", "0.30", "NaN", 1), "gross_weight"),
        (roll("Infinity", "0.30", "Infinity", 1), "gross_weight"),
        (roll("10.00", None, "9.70", 1), "tare_weight"),
        (roll("10.00", "-0.10", "10.10", 1), "tare_weight"),
        (roll("10.00", "0.30", None, 1), "net_weight"),
        (roll("10.00", "0.30", "-1.00", 1), "net_weight"),
        (roll("10.00", "0.30", "9.71", 1), "net_weight"),
        (roll("10.00", "0.30", "9.70", 0), "pallet_number"),
        (roll("10.00", "0.30", "9.70", 1000), "pallet_number"),
        (roll("10.00", "0.30", "9.70", "7"), "pallet_number"),
        (roll("10.00", "0.30", "9.70", True), "pallet_number"),
    ],
)
def test_pallet_summary_rejects_unusable_saved_roll_data(entry, field_name):
    with pytest.raises(PalletSummaryDataError, match=field_name):
        build_terminal_pallet_summary([entry])


def test_pallet_summary_skips_wholly_unentered_rolls_before_validating_fields():
    summary = build_terminal_pallet_summary([
        roll(None, None, None, "not a saved pallet"),
        roll("10.00", "0.30", pallet=1),
    ])

    assert summary["total"]["roll_count"] == 1
