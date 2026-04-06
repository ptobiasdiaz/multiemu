from __future__ import annotations

"""Checks for frontend keymap regressions."""

import json

import pygame

from frontend.keymap import (
    CPC_PYGAME_KEYMAP,
    KIM1_PYGAME_KEYMAP,
    PYGAME_KEYMAPS,
    VIC20_PYGAME_KEYMAP,
    get_pygame_combo_keymap,
    get_pygame_unicode_combo_map,
    load_pygame_input_maps,
    resolve_pygame_key_controls,
)


def test_cpc_return_is_not_mapped_to_z_position():
    assert CPC_PYGAME_KEYMAP[pygame.K_RETURN] == (2, 2)
    assert CPC_PYGAME_KEYMAP[pygame.K_RETURN] != CPC_PYGAME_KEYMAP[pygame.K_z]


def test_cpc_comma_and_period_are_not_swapped():
    assert CPC_PYGAME_KEYMAP[pygame.K_COMMA] == (4, 7)
    assert CPC_PYGAME_KEYMAP[pygame.K_PERIOD] == (3, 7)


def test_cpc_enter_and_brackets_match_the_matrix_positions():
    assert CPC_PYGAME_KEYMAP[pygame.K_RETURN] == (2, 2)
    assert CPC_PYGAME_KEYMAP[pygame.K_KP_ENTER] == (0, 6)
    assert CPC_PYGAME_KEYMAP[pygame.K_LEFTBRACKET] == (2, 1)
    assert CPC_PYGAME_KEYMAP[pygame.K_RIGHTBRACKET] == (2, 3)


def test_cpc_altgr_1_resolves_to_pipe_key():
    class _Event:
        key = pygame.K_1
        mod = pygame.KMOD_MODE

    controls = resolve_pygame_key_controls(
        CPC_PYGAME_KEYMAP,
        get_pygame_combo_keymap("cpc"),
        get_pygame_unicode_combo_map("cpc"),
        _Event(),
    )

    assert controls == ((2, 5), (3, 2))


def test_cpc_altgr_1_also_resolves_when_pygame_reports_right_alt_only():
    class _Event:
        key = pygame.K_1
        mod = pygame.KMOD_RALT

    controls = resolve_pygame_key_controls(
        CPC_PYGAME_KEYMAP,
        get_pygame_combo_keymap("cpc"),
        get_pygame_unicode_combo_map("cpc"),
        _Event(),
    )

    assert controls == ((2, 5), (3, 2))


def test_spectrum_host_arrow_keys_resolve_to_caps_shift_cursor_combos():
    class _Left:
        key = pygame.K_LEFT
        mod = 0

    class _Up:
        key = pygame.K_UP
        mod = 0

    left_controls = resolve_pygame_key_controls(
        PYGAME_KEYMAPS["spectrum128k"],
        get_pygame_combo_keymap("spectrum128k"),
        get_pygame_unicode_combo_map("spectrum128k"),
        _Left(),
    )
    up_controls = resolve_pygame_key_controls(
        PYGAME_KEYMAPS["spectrum128k"],
        get_pygame_combo_keymap("spectrum128k"),
        get_pygame_unicode_combo_map("spectrum128k"),
        _Up(),
    )

    assert left_controls == ((0, 0), (3, 4))
    assert up_controls == ((0, 0), (4, 3))


def test_spectrum48k_backspace_resolves_to_caps_shift_zero_combo():
    class _Backspace:
        key = pygame.K_BACKSPACE
        mod = 0

    controls = resolve_pygame_key_controls(
        PYGAME_KEYMAPS["spectrum48k"],
        get_pygame_combo_keymap("spectrum48k"),
        get_pygame_unicode_combo_map("spectrum48k"),
        _Backspace(),
    )

    assert controls == ((0, 0), (4, 0))


def test_spectrum_editor_punctuation_and_backspace_resolve_to_expected_combos():
    class _Backspace:
        key = pygame.K_BACKSPACE
        mod = 0

    class _Comma:
        key = pygame.K_COMMA
        mod = 0

    class _Period:
        key = pygame.K_PERIOD
        mod = 0

    backspace_controls = resolve_pygame_key_controls(
        PYGAME_KEYMAPS["spectrum128k"],
        get_pygame_combo_keymap("spectrum128k"),
        get_pygame_unicode_combo_map("spectrum128k"),
        _Backspace(),
    )
    comma_controls = resolve_pygame_key_controls(
        PYGAME_KEYMAPS["spectrum128k"],
        get_pygame_combo_keymap("spectrum128k"),
        get_pygame_unicode_combo_map("spectrum128k"),
        _Comma(),
    )
    period_controls = resolve_pygame_key_controls(
        PYGAME_KEYMAPS["spectrum128k"],
        get_pygame_combo_keymap("spectrum128k"),
        get_pygame_unicode_combo_map("spectrum128k"),
        _Period(),
    )

    assert backspace_controls == ((0, 0), (4, 0))
    assert comma_controls == ((7, 1), (7, 3))
    assert period_controls == ((7, 1), (7, 2))


def test_spectrum_shifted_symbols_resolve_via_unicode_mapping():
    class _Exclaim:
        key = pygame.K_1
        mod = pygame.KMOD_SHIFT
        unicode = "!"

    class _Plus:
        key = pygame.K_EQUALS
        mod = pygame.KMOD_SHIFT
        unicode = "+"

    class _Minus:
        key = pygame.K_MINUS
        mod = 0
        unicode = "-"

    exclaim_controls = resolve_pygame_key_controls(
        PYGAME_KEYMAPS["spectrum128k"],
        get_pygame_combo_keymap("spectrum128k"),
        get_pygame_unicode_combo_map("spectrum128k"),
        _Exclaim(),
    )
    plus_controls = resolve_pygame_key_controls(
        PYGAME_KEYMAPS["spectrum128k"],
        get_pygame_combo_keymap("spectrum128k"),
        get_pygame_unicode_combo_map("spectrum128k"),
        _Plus(),
    )
    minus_controls = resolve_pygame_key_controls(
        PYGAME_KEYMAPS["spectrum128k"],
        get_pygame_combo_keymap("spectrum128k"),
        get_pygame_unicode_combo_map("spectrum128k"),
        _Minus(),
    )

    assert exclaim_controls == ((7, 1), (3, 0))
    assert plus_controls == ((7, 1), (6, 2))
    assert minus_controls == ((7, 1), (6, 3))


def test_spectrum_spanish_layout_shift7_and_shift0_resolve_to_expected_symbols():
    class _Slash:
        key = pygame.K_7
        mod = pygame.KMOD_SHIFT
        unicode = "/"

    class _Equals:
        key = pygame.K_0
        mod = pygame.KMOD_SHIFT
        unicode = "="

    slash_controls = resolve_pygame_key_controls(
        PYGAME_KEYMAPS["spectrum128k"],
        get_pygame_combo_keymap("spectrum128k"),
        get_pygame_unicode_combo_map("spectrum128k"),
        _Slash(),
    )
    equals_controls = resolve_pygame_key_controls(
        PYGAME_KEYMAPS["spectrum128k"],
        get_pygame_combo_keymap("spectrum128k"),
        get_pygame_unicode_combo_map("spectrum128k"),
        _Equals(),
    )

    assert slash_controls == ((7, 1), (0, 4))
    assert equals_controls == ((7, 1), (6, 1))


def test_custom_keymap_file_can_override_default_machine_mapping(tmp_path):
    keymap_path = tmp_path / "spectrum_es.json"
    keymap_path.write_text(
        json.dumps(
            {
                "id": "spectrum_es",
                "base": "spectrum128k",
                "keys": {"K_a": [9, 9]},
                "unicode_combos": {"/": [[7, 1], [7, 4]]},
            }
        ),
        encoding="utf-8",
    )

    maps = load_pygame_input_maps("spectrum128k", keymap_file=str(keymap_path))

    assert maps.keymap[pygame.K_a] == (9, 9)
    assert maps.unicode_combo_keymap["/"] == ((7, 1), (7, 4))
    assert maps.combo_keymap[(pygame.K_LEFT, 0)] == ((0, 0), (3, 4))


def test_spectrum_shifted_digit_keys_resolve_to_symbol_shift_number_row():
    class _Shift2:
        key = pygame.K_2
        mod = pygame.KMOD_SHIFT
        unicode = ""

    class _Shift3:
        key = pygame.K_3
        mod = pygame.KMOD_SHIFT
        unicode = ""

    shift2_controls = resolve_pygame_key_controls(
        PYGAME_KEYMAPS["spectrum128k"],
        get_pygame_combo_keymap("spectrum128k"),
        get_pygame_unicode_combo_map("spectrum128k"),
        _Shift2(),
    )
    shift3_controls = resolve_pygame_key_controls(
        PYGAME_KEYMAPS["spectrum128k"],
        get_pygame_combo_keymap("spectrum128k"),
        get_pygame_unicode_combo_map("spectrum128k"),
        _Shift3(),
    )

    assert shift2_controls == ((7, 1), (3, 1))
    assert shift3_controls == ((7, 1), (3, 2))


def test_kim1_keymap_keeps_hex_digits_and_commands_distinct():
    assert KIM1_PYGAME_KEYMAP[pygame.K_KP0] == (0, 6)
    assert KIM1_PYGAME_KEYMAP[pygame.K_KP7] == (1, 6)
    assert KIM1_PYGAME_KEYMAP[pygame.K_f] == (2, 5)
    assert KIM1_PYGAME_KEYMAP[pygame.K_KP_ENTER] == (2, 1)


def test_vic20_keymap_exposes_basic_matrix_navigation_and_actions():
    assert VIC20_PYGAME_KEYMAP[pygame.K_a] == (1, 2)
    assert VIC20_PYGAME_KEYMAP[pygame.K_q] == (0, 6)
    assert VIC20_PYGAME_KEYMAP[pygame.K_1] == (0, 0)
    assert VIC20_PYGAME_KEYMAP[pygame.K_RETURN] == (7, 1)
    assert VIC20_PYGAME_KEYMAP[pygame.K_SPACE] == (0, 4)
    assert VIC20_PYGAME_KEYMAP[pygame.K_ESCAPE] == (0, 3)
    assert VIC20_PYGAME_KEYMAP[pygame.K_LALT] == (0, 5)
    assert VIC20_PYGAME_KEYMAP[pygame.K_DOWN] == (7, 3)
