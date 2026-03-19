from __future__ import annotations

import pygame


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


PYGAME_KEYMAPS = {
    "spectrum": SPECTRUM_PYGAME_KEYMAP,
    "cpc": CPC_PYGAME_KEYMAP,
}


def get_pygame_keymap(name: str | None):
    """Return the requested pygame keymap or the Spectrum default."""

    if name is None:
        return SPECTRUM_PYGAME_KEYMAP
    return PYGAME_KEYMAPS.get(name, SPECTRUM_PYGAME_KEYMAP)
