from __future__ import annotations

import pygame
from frontend.input_events import (
    JOYSTICK_DOWN,
    JOYSTICK_FIRE,
    JOYSTICK_FIRE_2,
    JOYSTICK_LEFT,
    JOYSTICK_RIGHT,
    JOYSTICK_UP,
)


SPECTRUM_PYGAME_KEYMAP = {
    pygame.K_LSHIFT: (0, 0),
    pygame.K_z: (0, 1),
    pygame.K_x: (0, 2),
    pygame.K_c: (0, 3),
    pygame.K_v: (0, 4),
    pygame.K_a: (1, 0),
    pygame.K_s: (1, 1),
    pygame.K_d: (1, 2),
    pygame.K_f: (1, 3),
    pygame.K_g: (1, 4),
    pygame.K_q: (2, 0),
    pygame.K_w: (2, 1),
    pygame.K_e: (2, 2),
    pygame.K_r: (2, 3),
    pygame.K_t: (2, 4),
    pygame.K_1: (3, 0),
    pygame.K_2: (3, 1),
    pygame.K_3: (3, 2),
    pygame.K_4: (3, 3),
    pygame.K_5: (3, 4),
    pygame.K_0: (4, 0),
    pygame.K_9: (4, 1),
    pygame.K_8: (4, 2),
    pygame.K_7: (4, 3),
    pygame.K_6: (4, 4),
    pygame.K_p: (5, 0),
    pygame.K_o: (5, 1),
    pygame.K_i: (5, 2),
    pygame.K_u: (5, 3),
    pygame.K_y: (5, 4),
    pygame.K_RETURN: (6, 0),
    pygame.K_l: (6, 1),
    pygame.K_k: (6, 2),
    pygame.K_j: (6, 3),
    pygame.K_h: (6, 4),
    pygame.K_SPACE: (7, 0),
    pygame.K_RCTRL: (7, 1),
    pygame.K_m: (7, 2),
    pygame.K_n: (7, 3),
    pygame.K_b: (7, 4),
}


# The CPC matrix is 10x8. Coordinates are expressed as (line, bit), matching
# the scan layout expected by the firmware through the PSG keyboard port.
CPC_PYGAME_KEYMAP = {
    pygame.K_UP: (0, 0),
    pygame.K_RIGHT: (0, 1),
    pygame.K_DOWN: (0, 2),
    pygame.K_LEFT: (1, 0),
    pygame.K_KP_ENTER: (0, 6),
    pygame.K_LCTRL: (2, 7),
    pygame.K_RCTRL: (2, 7),
    pygame.K_BACKSLASH: (2, 6),
    pygame.K_LSHIFT: (2, 5),
    pygame.K_RSHIFT: (2, 5),
    pygame.K_RIGHTBRACKET: (2, 3),
    pygame.K_RETURN: (2, 2),
    pygame.K_LEFTBRACKET: (2, 1),
    pygame.K_BACKSPACE: (9, 7),
    pygame.K_COMMA: (4, 7),
    pygame.K_SLASH: (3, 6),
    pygame.K_SEMICOLON: (3, 4),
    pygame.K_p: (3, 3),
    pygame.K_MINUS: (3, 1),
    pygame.K_PERIOD: (3, 7),
    pygame.K_m: (4, 6),
    pygame.K_k: (4, 5),
    pygame.K_l: (4, 4),
    pygame.K_i: (4, 3),
    pygame.K_o: (4, 2),
    pygame.K_9: (4, 1),
    pygame.K_0: (4, 0),
    pygame.K_SPACE: (5, 7),
    pygame.K_n: (5, 6),
    pygame.K_j: (5, 5),
    pygame.K_h: (5, 4),
    pygame.K_y: (5, 3),
    pygame.K_u: (5, 2),
    pygame.K_7: (5, 1),
    pygame.K_8: (5, 0),
    pygame.K_v: (6, 7),
    pygame.K_b: (6, 6),
    pygame.K_f: (6, 5),
    pygame.K_g: (6, 4),
    pygame.K_t: (6, 3),
    pygame.K_r: (6, 2),
    pygame.K_5: (6, 1),
    pygame.K_6: (6, 0),
    pygame.K_x: (7, 7),
    pygame.K_c: (7, 6),
    pygame.K_d: (7, 5),
    pygame.K_s: (7, 4),
    pygame.K_w: (7, 3),
    pygame.K_e: (7, 2),
    pygame.K_3: (7, 1),
    pygame.K_4: (7, 0),
    pygame.K_z: (8, 7),
    pygame.K_CAPSLOCK: (8, 6),
    pygame.K_a: (8, 5),
    pygame.K_TAB: (8, 4),
    pygame.K_q: (8, 3),
    pygame.K_ESCAPE: (8, 2),
    pygame.K_2: (8, 1),
    pygame.K_1: (8, 0),
    pygame.K_DELETE: (9, 7),
    pygame.K_KP_PERIOD: (9, 6),
}

GAMEBOY_PYGAME_KEYMAP = {
    pygame.K_RIGHT: (0, 0),
    pygame.K_LEFT: (0, 1),
    pygame.K_UP: (0, 2),
    pygame.K_DOWN: (0, 3),
    pygame.K_z: (1, 0),
    pygame.K_LALT: (1, 0),
    pygame.K_x: (1, 1),
    pygame.K_LCTRL: (1, 1),
    pygame.K_BACKSPACE: (1, 2),
    pygame.K_SPACE: (1, 2),
    pygame.K_RETURN: (1, 3),
    pygame.K_RSHIFT: (1, 3),
}

KIM1_PYGAME_KEYMAP = {
    pygame.K_KP0: (0, 6),
    pygame.K_KP1: (0, 5),
    pygame.K_KP2: (0, 4),
    pygame.K_KP3: (0, 3),
    pygame.K_KP4: (0, 2),
    pygame.K_KP5: (0, 1),
    pygame.K_KP6: (0, 0),
    pygame.K_KP7: (1, 6),
    pygame.K_KP8: (1, 5),
    pygame.K_KP9: (1, 4),
    pygame.K_a: (1, 3),
    pygame.K_b: (1, 2),
    pygame.K_c: (1, 1),
    pygame.K_d: (1, 0),
    pygame.K_e: (2, 6),
    pygame.K_f: (2, 5),
    pygame.K_KP_MINUS: (2, 4),
    pygame.K_KP_PERIOD: (2, 3),
    pygame.K_KP_PLUS: (2, 2),
    pygame.K_KP_ENTER: (2, 1),
    pygame.K_KP_DIVIDE: (2, 0),
}


# VIC-20 keyboard matrix expressed as (row, column). The KERNAL key tables are
# laid out by column, so each 8-byte group in the ROM maps to one matrix
# column, with the byte position inside the group selecting the row.
VIC20_PYGAME_KEYMAP = {
    pygame.K_1: (0, 0),
    pygame.K_3: (1, 0),
    pygame.K_5: (2, 0),
    pygame.K_7: (3, 0),
    pygame.K_9: (4, 0),
    pygame.K_KP_PLUS: (5, 0),
    pygame.K_BACKQUOTE: (6, 0),
    pygame.K_BACKSPACE: (7, 0),
    pygame.K_LEFTBRACKET: (0, 1),
    pygame.K_w: (1, 1),
    pygame.K_r: (2, 1),
    pygame.K_y: (3, 1),
    pygame.K_i: (4, 1),
    pygame.K_p: (5, 1),
    pygame.K_RIGHTBRACKET: (6, 1),
    pygame.K_RETURN: (7, 1),
    pygame.K_LCTRL: (0, 2),
    pygame.K_a: (1, 2),
    pygame.K_d: (2, 2),
    pygame.K_g: (3, 2),
    pygame.K_j: (4, 2),
    pygame.K_l: (5, 2),
    pygame.K_SEMICOLON: (6, 2),
    pygame.K_RIGHT: (7, 2),
    pygame.K_ESCAPE: (0, 3),
    pygame.K_LSHIFT: (1, 3),
    pygame.K_x: (2, 3),
    pygame.K_v: (3, 3),
    pygame.K_n: (4, 3),
    pygame.K_COMMA: (5, 3),
    pygame.K_SLASH: (6, 3),
    pygame.K_DOWN: (7, 3),
    pygame.K_SPACE: (0, 4),
    pygame.K_z: (1, 4),
    pygame.K_c: (2, 4),
    pygame.K_b: (3, 4),
    pygame.K_m: (4, 4),
    pygame.K_PERIOD: (5, 4),
    pygame.K_RSHIFT: (6, 4),
    pygame.K_F1: (7, 4),
    pygame.K_LALT: (0, 5),
    pygame.K_s: (1, 5),
    pygame.K_f: (2, 5),
    pygame.K_h: (3, 5),
    pygame.K_k: (4, 5),
    pygame.K_QUOTE: (5, 5),
    pygame.K_EQUALS: (6, 5),
    pygame.K_F3: (7, 5),
    pygame.K_q: (0, 6),
    pygame.K_e: (1, 6),
    pygame.K_t: (2, 6),
    pygame.K_u: (3, 6),
    pygame.K_o: (4, 6),
    pygame.K_UP: (5, 6),
    pygame.K_CARET: (6, 6),
    pygame.K_F5: (7, 6),
    pygame.K_2: (0, 7),
    pygame.K_4: (1, 7),
    pygame.K_6: (2, 7),
    pygame.K_8: (3, 7),
    pygame.K_0: (4, 7),
    pygame.K_MINUS: (5, 7),
    pygame.K_HOME: (6, 7),
    pygame.K_DELETE: (7, 0),
    pygame.K_LEFT: (7, 2),
    pygame.K_F7: (7, 7),
}


PYGAME_KEYMAPS = {
    "spectrum": SPECTRUM_PYGAME_KEYMAP,
    "cpc": CPC_PYGAME_KEYMAP,
    "gameboy": GAMEBOY_PYGAME_KEYMAP,
    "kim1": KIM1_PYGAME_KEYMAP,
    "vic20": VIC20_PYGAME_KEYMAP,
}


SPECTRUM_PYGAME_GAMEPAD_MAP = {
    "dpad_left": JOYSTICK_LEFT,
    "dpad_down": JOYSTICK_DOWN,
    "dpad_up": JOYSTICK_UP,
    "dpad_right": JOYSTICK_RIGHT,
    "button_south": JOYSTICK_FIRE,
    "button_east": JOYSTICK_FIRE_2,
    "button_start": JOYSTICK_FIRE,
    "button_select": JOYSTICK_FIRE_2,
}

CPC_PYGAME_GAMEPAD_MAP = {
    "dpad_up": JOYSTICK_UP,
    "dpad_right": JOYSTICK_RIGHT,
    "dpad_down": JOYSTICK_DOWN,
    "dpad_left": JOYSTICK_LEFT,
    "button_south": JOYSTICK_FIRE,
    "button_east": JOYSTICK_FIRE_2,
    "button_start": JOYSTICK_FIRE,
}

GAMEBOY_PYGAME_GAMEPAD_MAP = {
    "dpad_right": (0, 0),
    "dpad_left": (0, 1),
    "dpad_up": (0, 2),
    "dpad_down": (0, 3),
    "button_south": (1, 0),  # A
    "button_east": (1, 1),   # B
    "button_select": (1, 2),
    "button_start": (1, 3),
}

VIC20_PYGAME_GAMEPAD_MAP = {
    "dpad_right": JOYSTICK_RIGHT,
    "dpad_left": JOYSTICK_LEFT,
    "dpad_down": JOYSTICK_DOWN,
    "dpad_up": JOYSTICK_UP,
    "button_south": JOYSTICK_FIRE,
    "button_start": JOYSTICK_FIRE_2,
}


PYGAME_GAMEPAD_MAPS = {
    "spectrum": SPECTRUM_PYGAME_GAMEPAD_MAP,
    "cpc": CPC_PYGAME_GAMEPAD_MAP,
    "gameboy": GAMEBOY_PYGAME_GAMEPAD_MAP,
    "vic20": VIC20_PYGAME_GAMEPAD_MAP,
}


def get_pygame_keymap(name: str | None):
    """Return the requested pygame keymap or the Spectrum default."""

    if name is None:
        return SPECTRUM_PYGAME_KEYMAP
    return PYGAME_KEYMAPS.get(name, SPECTRUM_PYGAME_KEYMAP)


def get_pygame_gamepad_map(name: str | None):
    """Return the requested pygame gamepad map or an empty mapping."""

    if name is None:
        return {}
    return PYGAME_GAMEPAD_MAPS.get(name, {})
