from __future__ import annotations

from devices import CPCDiskImage, CPCFDC
from machines.z80 import CPC464


def _make_standard_dsk() -> bytes:
    disk_header = bytearray(0x100)
    signature = b"MV - CPCEMU Disk-File\r\nDisk-Info\r\n"
    disk_header[:len(signature)] = signature
    disk_header[0x30] = 1  # tracks
    disk_header[0x31] = 1  # sides
    disk_header[0x32] = 0x00
    disk_header[0x33] = 0x03

    track_header = bytearray(0x100)
    track_signature = b"Track-Info\r\n"
    track_header[:len(track_signature)] = track_signature
    track_header[0x10] = 0
    track_header[0x11] = 0
    track_header[0x14] = 2  # 512-byte sectors
    track_header[0x15] = 1
    track_header[0x16] = 0x2A
    track_header[0x17] = 0xE5
    track_header[0x18] = 0
    track_header[0x19] = 0
    track_header[0x1A] = 0xC1
    track_header[0x1B] = 2
    track_header[0x1C] = 0
    track_header[0x1D] = 0

    sector_data = bytes((index & 0xFF) for index in range(512))
    return bytes(disk_header + track_header + sector_data)


def _make_standard_dsk_with_cpcemu_timestamp_header() -> bytes:
    data = bytearray(_make_standard_dsk())
    alt_header = b"MV - CPCEMU / 08 Jul 14 21:17\x00"
    data[:len(alt_header)] = alt_header
    return bytes(data)


def test_cpc_disk_image_parses_standard_dsk_sector():
    image = CPCDiskImage.from_dsk_bytes(_make_standard_dsk())

    sector = image.get_sector(0, 0, 0xC1)

    assert sector is not None
    assert sector.c == 0
    assert sector.h == 0
    assert sector.r == 0xC1
    assert sector.n == 2
    assert len(sector.data) == 512
    assert sector.data[:4] == bytes([0x00, 0x01, 0x02, 0x03])


def test_cpc_disk_image_uses_standard_track_size_in_bytes_without_extra_scaling():
    data = _make_standard_dsk()

    image = CPCDiskImage.from_dsk_bytes(data)

    assert image.get_track(0, 0) is not None


def test_cpc_disk_image_accepts_cpcemu_timestamp_standard_header_variant():
    image = CPCDiskImage.from_dsk_bytes(_make_standard_dsk_with_cpcemu_timestamp_header())

    assert image.get_track(0, 0) is not None


def test_cpc_fdc_can_report_id_and_stream_sector_data():
    image = CPCDiskImage.from_dsk_bytes(_make_standard_dsk())
    fdc = CPCFDC(image)

    fdc.write_data(0x0A)
    fdc.write_data(0x00)
    assert fdc.read_main_status() & 0x40
    read_id_result = [fdc.read_data() for _ in range(7)]
    assert read_id_result == [0x00, 0x00, 0x00, 0x00, 0x00, 0xC1, 0x02]

    for value in (0x06, 0x00, 0x00, 0x00, 0xC1, 0x02, 0xC1, 0x2A, 0xFF):
        fdc.write_data(value)

    payload = [fdc.read_data() for _ in range(512)]
    result = [fdc.read_data() for _ in range(7)]
    assert payload[:4] == [0x00, 0x01, 0x02, 0x03]
    assert result == [0x00, 0x00, 0x00, 0x00, 0x00, 0xC1, 0x02]


def test_cpc464_can_switch_upper_rom_banks_and_expose_fdc_ports():
    os_rom = bytes([0x00] * 0x4000)
    basic_rom = bytes([0x42] * 0x4000)
    amsdos_rom = bytes([0x99] * 0x4000)
    machine = CPC464(
        os_rom,
        basic_rom_data=basic_rom,
        amsdos_rom_data=amsdos_rom,
        disk_data=_make_standard_dsk(),
    )

    assert machine.peek(0xC000) == 0x42
    machine._port_write(0xDF00, 7)
    assert machine.peek(0xC000) == 0x99

    assert machine._port_read(0xFB7E) == 0x80
    machine._port_write(0xFB7E, 0x01)
    assert machine.fdc.motor_on is True
