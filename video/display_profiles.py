from __future__ import annotations

"""Shared monitor/display profiles for machine framebuffer presentation.

The emulator core should describe the machine raster, while the presentation
layer decides how much border or overscan is exposed to the user. These
profiles are intentionally small for now: they provide a common vocabulary
shared by CPC and Spectrum without forcing the CLI to expose profile selection
yet.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DisplayProfile:
    """Describe how a machine raster should be presented to the user."""

    profile_id: str
    description: str
    spectrum_border_left: int | None = None
    spectrum_border_right: int | None = None
    spectrum_border_top: int | None = None
    spectrum_border_bottom: int | None = None
    cpc_frame_width: int | None = None
    cpc_frame_height: int | None = None
    cpc_raster_view_x: int | None = None
    cpc_raster_shift_y: int | None = None


DISPLAY_PROFILES: dict[str, DisplayProfile] = {
    "default": DisplayProfile(
        profile_id="default",
        description="Balanced centered viewport with a practical amount of border",
        spectrum_border_left=48,
        spectrum_border_right=48,
        spectrum_border_top=48,
        spectrum_border_bottom=56,
        cpc_frame_width=384,
        cpc_frame_height=272,
        cpc_raster_view_x=48,
        cpc_raster_shift_y=0,
    ),
    "full-border": DisplayProfile(
        profile_id="full-border",
        description="Expose more border and overscan around the active area",
        spectrum_border_left=64,
        spectrum_border_right=64,
        spectrum_border_top=56,
        spectrum_border_bottom=64,
        cpc_frame_width=448,
        cpc_frame_height=312,
        cpc_raster_view_x=16,
        cpc_raster_shift_y=0,
    ),
}


def get_display_profile(profile_id: str = "default") -> DisplayProfile:
    """Return a named display profile or raise a user-facing error."""

    try:
        return DISPLAY_PROFILES[profile_id]
    except KeyError as exc:
        supported = ", ".join(sorted(DISPLAY_PROFILES))
        raise ValueError(
            f"perfil de display no soportado: {profile_id!r}. Disponibles: {supported}"
        ) from exc


def list_display_profiles() -> list[DisplayProfile]:
    """Return known profiles in stable order."""

    return [DISPLAY_PROFILES[key] for key in sorted(DISPLAY_PROFILES)]
