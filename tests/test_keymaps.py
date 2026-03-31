from __future__ import annotations

"""Checks for frontend keymap regressions."""

import pygame

from frontend.keymap import CPC_PYGAME_KEYMAP, KIM1_PYGAME_KEYMAP, VIC20_PYGAME_KEYMAP


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
