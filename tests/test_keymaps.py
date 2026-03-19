from __future__ import annotations

"""Checks for frontend keymap regressions."""

import pygame

from frontend.keymap import CPC_PYGAME_KEYMAP


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
