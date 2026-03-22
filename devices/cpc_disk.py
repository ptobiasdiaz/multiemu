from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CPCDiskSector:
    c: int
    h: int
    r: int
    n: int
    st1: int
    st2: int
    data: bytes


@dataclass(slots=True)
class CPCDiskTrack:
    track: int
    side: int
    sectors: tuple[CPCDiskSector, ...]


class CPCDiskImage:
    """Parse standard/extended CPC DSK images into track/sector objects."""

    def __init__(self, tracks: dict[tuple[int, int], CPCDiskTrack]):
        self.tracks = tracks

    @classmethod
    def from_dsk_bytes(cls, data: bytes) -> "CPCDiskImage":
        if len(data) < 0x100:
            raise ValueError("imagen DSK demasiado pequeña")

        header = data[:0x100]
        is_extended = header.startswith(b"EXTENDED CPC DSK")
        is_standard = header.startswith(b"MV - CPCEMU Disk-File")
        if not is_standard and not is_extended:
            raise ValueError("cabecera DSK no soportada")

        track_count = header[0x30]
        side_count = header[0x31]
        if track_count == 0 or side_count == 0:
            raise ValueError("imagen DSK sin pistas")

        track_sizes = []
        if is_extended:
            for entry in header[0x34:0x34 + track_count * side_count]:
                track_sizes.append(entry * 0x100)
        else:
            # Standard DSK stores the per-track size directly in bytes.
            track_size = header[0x32] | (header[0x33] << 8)
            track_sizes = [track_size] * (track_count * side_count)

        tracks: dict[tuple[int, int], CPCDiskTrack] = {}
        offset = 0x100
        for raw_index, track_size in enumerate(track_sizes):
            if track_size == 0:
                continue
            track_data = data[offset:offset + track_size]
            if len(track_data) < 0x100:
                raise ValueError("bloque de pista DSK truncado")

            track_header = track_data[:0x100]
            if not track_header.startswith(b"Track-Info"):
                raise ValueError("cabecera de pista DSK no soportada")

            track_no = track_header[0x10]
            side_no = track_header[0x11]
            sector_size_code = track_header[0x14]
            sector_count = track_header[0x15]
            default_sector_size = 0x80 << sector_size_code

            sectors = []
            sector_data_offset = 0x100
            for sector_index in range(sector_count):
                info_offset = 0x18 + sector_index * 8
                c = track_header[info_offset + 0]
                h = track_header[info_offset + 1]
                r = track_header[info_offset + 2]
                n = track_header[info_offset + 3]
                st1 = track_header[info_offset + 4]
                st2 = track_header[info_offset + 5]
                if is_extended:
                    sector_size = track_header[info_offset + 6] | (track_header[info_offset + 7] << 8)
                else:
                    sector_size = default_sector_size
                sector_bytes = track_data[sector_data_offset:sector_data_offset + sector_size]
                if len(sector_bytes) != sector_size:
                    raise ValueError("datos de sector DSK truncados")
                sectors.append(
                    CPCDiskSector(
                        c=c,
                        h=h,
                        r=r,
                        n=n,
                        st1=st1,
                        st2=st2,
                        data=bytes(sector_bytes),
                    )
                )
                sector_data_offset += sector_size

            tracks[(track_no, side_no)] = CPCDiskTrack(track=track_no, side=side_no, sectors=tuple(sectors))
            offset += track_size

        return cls(tracks)

    def get_track(self, track: int, side: int = 0) -> CPCDiskTrack | None:
        return self.tracks.get((track & 0xFF, side & 0xFF))

    def get_sector(self, track: int, side: int, sector_id: int) -> CPCDiskSector | None:
        disk_track = self.get_track(track, side)
        if disk_track is None:
            return None
        for sector in disk_track.sectors:
            if sector.r == (sector_id & 0xFF):
                return sector
        return None
