from __future__ import annotations

"""Checks for shared display profile wiring across machine families."""

from machines.z80 import CPC464, Spectrum48K
from video import get_display_profile


def test_default_display_profile_is_shared_between_machine_families():
    profile = get_display_profile("default")

    cpc = CPC464(bytes([0x00]) * 0x4000)
    spectrum = Spectrum48K(bytes([0x00]) * 0x4000)

    assert cpc.display_profile.profile_id == profile.profile_id
    assert spectrum.display_profile.profile_id == profile.profile_id


def test_full_border_profile_changes_machine_frame_geometry():
    cpc = CPC464(bytes([0x00]) * 0x4000, display_profile="full-border")
    spectrum = Spectrum48K(bytes([0x00]) * 0x4000, display_profile="full-border")

    assert cpc.frame_width == 448
    assert cpc.frame_height == 312
    assert spectrum.ula.frame_width > spectrum.ula.SCREEN_WIDTH
    assert spectrum.ula.frame_height > spectrum.ula.SCREEN_HEIGHT
