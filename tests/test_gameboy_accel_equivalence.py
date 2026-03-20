from __future__ import annotations

from devices.gameboy import GameBoyAPU, GameBoyDMAController, GameBoyPPU, GameBoyTimer
from devices.gameboy.cartridge import GameBoyCartridge
from devices.gameboy.interrupts import GameBoyInterruptController
from devices.gameboy.mbc1 import MBC1
from devices.gameboy.mbc2 import MBC2
from devices.gameboy.mbc3 import MBC3
from devices.gameboy.mbc5 import MBC5
from tests.fallbacks.gameboy_apu_reference import GameBoyAPU as GameBoyAPUReference
from tests.fallbacks.gameboy_cartridge_reference import (
    GameBoyCartridge as GameBoyCartridgeReference,
)
from tests.fallbacks.gameboy_dma_reference import (
    GameBoyDMAController as GameBoyDMAControllerReference,
)
from tests.fallbacks.gameboy_interrupts_reference import (
    GameBoyInterruptController as GameBoyInterruptControllerReference,
)
from tests.fallbacks.gameboy_mbc1_reference import MBC1 as MBC1Reference
from tests.fallbacks.gameboy_mbc2_reference import MBC2 as MBC2Reference
from tests.fallbacks.gameboy_mbc3_reference import MBC3 as MBC3Reference
from tests.fallbacks.gameboy_mbc5_reference import MBC5 as MBC5Reference
from tests.fallbacks.gameboy_ppu_reference import GameBoyPPU as GameBoyPPUReference
from tests.fallbacks.gameboy_timer_reference import GameBoyTimer as GameBoyTimerReference


def _make_test_rom(
    *,
    bank_count: int = 2,
    title: str = "REFTEST",
    cartridge_type: int = 0x00,
    ram_size_code: int = 0x00,
) -> bytes:
    rom = bytearray(bank_count * 0x4000)
    for bank in range(bank_count):
        start = bank * 0x4000
        rom[start : start + 0x4000] = bytes([bank & 0xFF]) * 0x4000

    title_bytes = title.encode("ascii")[:16]
    rom[0x0134 : 0x0134 + len(title_bytes)] = title_bytes
    rom[0x0147] = cartridge_type
    rom[0x0148] = {
        2: 0x00,
        4: 0x01,
        8: 0x02,
        16: 0x03,
        32: 0x04,
        64: 0x05,
        128: 0x06,
        256: 0x07,
        512: 0x08,
    }.get(bank_count, 0x00)
    rom[0x0149] = ram_size_code
    return bytes(rom)


class _FakePPUBus:
    def __init__(self):
        self.vram = bytearray(0x2000)
        self.oam = bytearray(0xA0)
        self.vram_accessible = True
        self.oam_accessible = True

    def set_ppu_access(self, *, vram_accessible: bool, oam_accessible: bool) -> None:
        self.vram_accessible = vram_accessible
        self.oam_accessible = oam_accessible

    def set_dma_oam_blocked(self, blocked: bool) -> None:
        self.oam_accessible = not blocked


def test_gameboy_timer_accel_matches_reference():
    accel_interrupts = GameBoyInterruptController()
    ref_interrupts = GameBoyInterruptController()
    accel = GameBoyTimer(accel_interrupts)
    reference = GameBoyTimerReference(ref_interrupts)

    for timer in (accel, reference):
        timer.write_tma(0xAC)
        timer.write_tima(0xFE)
        timer.write_tac(0x05)
        timer.run_cycles(16)
        timer.run_cycles(16)
        timer.write_div(0x99)
        timer.run_cycles(64)

    assert accel.read_div() == reference.read_div()
    assert accel.read_tima() == reference.read_tima()
    assert accel.read_tma() == reference.read_tma()
    assert accel.read_tac() == reference.read_tac()
    assert accel_interrupts.interrupt_flags == ref_interrupts.interrupt_flags


def test_gameboy_apu_accel_matches_reference():
    accel = GameBoyAPU(sample_rate=8_000)
    reference = GameBoyAPUReference(sample_rate=8_000)

    for apu in (accel, reference):
        apu.write_nr52(0x80)
        apu.write_nr50(0x77)
        apu.write_nr51(0x55)
        for offset in range(16):
            apu.write_wave_ram(offset, 0x1F)
        apu.write_nr10(0x11)
        apu.write_nr11(0x80)
        apu.write_nr12(0xF0)
        apu.write_nr13(0x20)
        apu.write_nr14(0x87)
        apu.write_nr30(0x80)
        apu.write_nr31(0x40)
        apu.write_nr32(0x20)
        apu.write_nr33(0x40)
        apu.write_nr34(0x87)
        apu.begin_frame()
        apu.run_cycles(8_192)

    assert accel.read_nr52() == reference.read_nr52()
    assert accel.read_nr50() == reference.read_nr50()
    assert accel.read_nr51() == reference.read_nr51()
    assert list(accel.get_frame_samples()) == list(reference.get_frame_samples())


def test_gameboy_ppu_accel_matches_reference():
    accel_bus = _FakePPUBus()
    ref_bus = _FakePPUBus()
    accel_interrupts = GameBoyInterruptController()
    ref_interrupts = GameBoyInterruptController()
    accel = GameBoyPPU(accel_bus, accel_interrupts)
    reference = GameBoyPPUReference(ref_bus, ref_interrupts)

    for bus in (accel_bus, ref_bus):
        bus.vram[0x1800] = 0x01
        bus.vram[0x0010] = 0xAA
        bus.vram[0x0011] = 0x55
        bus.oam[0:4] = bytes((16, 8, 1, 0))

    for ppu in (accel, reference):
        ppu.write_lcdc(0x93)
        ppu.write_scx(3)
        ppu.write_scy(5)
        ppu.write_bgp(0xE4)
        ppu.write_obp0(0xD2)
        ppu.write_lyc(2)
        ppu.write_stat(ppu.read_stat() | 0x68)
        ppu.begin_frame()
        ppu.run_until(456 * 2 + 120)

    assert accel.read_ly() == reference.read_ly()
    assert accel.read_stat() == reference.read_stat()
    assert accel_interrupts.interrupt_flags == ref_interrupts.interrupt_flags
    assert accel_bus.vram_accessible == ref_bus.vram_accessible
    assert accel_bus.oam_accessible == ref_bus.oam_accessible
    assert accel.render_frame() == reference.render_frame()


def test_gameboy_mbc1_accel_matches_reference():
    rom = _make_test_rom(bank_count=8, cartridge_type=0x03, ram_size_code=0x03)
    accel = MBC1(rom, ram_size_code=0x03)
    reference = MBC1Reference(rom, ram_size_code=0x03)

    for mapper in (accel, reference):
        mapper.write(0x0000, 0x0A)
        mapper.write(0x2000, 0x02)
        mapper.write(0x4000, 0x01)
        mapper.write(0x6000, 0x01)
        mapper.write(0xA123, 0x5A)

    assert accel.read(0x0150) == reference.read(0x0150)
    assert accel.read(0x4000) == reference.read(0x4000)
    assert accel.read(0xA123) == reference.read(0xA123)


def test_gameboy_mbc2_accel_matches_reference():
    rom = _make_test_rom(bank_count=16, cartridge_type=0x05)
    accel = MBC2(rom)
    reference = MBC2Reference(rom)

    for mapper in (accel, reference):
        mapper.write(0x0000, 0x0A)
        mapper.write(0x2100, 0x03)
        mapper.write(0xA055, 0xBC)

    assert accel.read(0x4000) == reference.read(0x4000)
    assert accel.read(0xA055) == reference.read(0xA055)


def test_gameboy_mbc3_accel_matches_reference():
    rom = _make_test_rom(bank_count=16, cartridge_type=0x13, ram_size_code=0x03)
    accel = MBC3(rom, ram_size_code=0x03)
    reference = MBC3Reference(rom, ram_size_code=0x03)

    for mapper in (accel, reference):
        mapper.write(0x0000, 0x0A)
        mapper.write(0x2000, 0x03)
        mapper.write(0x4000, 0x01)
        mapper.write(0xA321, 0x66)
        mapper.write(0x4000, 0x08)
        mapper.write(0xA000, 0x12)

    assert accel.read(0x4000) == reference.read(0x4000)
    assert accel.read(0xA321) == reference.read(0xA321)
    accel.write(0x4000, 0x08)
    reference.write(0x4000, 0x08)
    assert accel.read(0xA000) == reference.read(0xA000)


def test_gameboy_mbc5_accel_matches_reference():
    rom = _make_test_rom(bank_count=32, cartridge_type=0x1B, ram_size_code=0x03)
    accel = MBC5(rom, ram_size_code=0x03)
    reference = MBC5Reference(rom, ram_size_code=0x03)

    for mapper in (accel, reference):
        mapper.write(0x0000, 0x0A)
        mapper.write(0x2000, 0x34)
        mapper.write(0x3000, 0x01)
        mapper.write(0x4000, 0x02)
        mapper.write(0xA010, 0x77)

    assert accel.read(0x4000) == reference.read(0x4000)
    assert accel.read(0xA010) == reference.read(0xA010)


def test_gameboy_cartridge_accel_matches_reference():
    rom = _make_test_rom(
        bank_count=32,
        title="PARITY",
        cartridge_type=0x1B,
        ram_size_code=0x03,
    )
    accel = GameBoyCartridge(rom)
    reference = GameBoyCartridgeReference(rom)

    accel.write(0x0000, 0x0A)
    reference.write(0x0000, 0x0A)
    accel.write(0x2000, 0x05)
    reference.write(0x2000, 0x05)
    accel.write(0xA111, 0x42)
    reference.write(0xA111, 0x42)

    assert accel.title == reference.title
    assert accel.cartridge_type == reference.cartridge_type
    assert accel.cartridge_type_name == reference.cartridge_type_name
    assert accel.supports_mbc5() == reference.supports_mbc5()
    assert accel.read(0x4000) == reference.read(0x4000)
    assert accel.read(0xA111) == reference.read(0xA111)


def test_gameboy_interrupts_accel_matches_reference():
    accel = GameBoyInterruptController()
    reference = GameBoyInterruptControllerReference()

    for controller in (accel, reference):
        controller.request(0)
        controller.request(2)
        controller.request(4)
        controller.acknowledge(2)

    assert accel.interrupt_enable == reference.interrupt_enable
    assert accel.interrupt_flags == reference.interrupt_flags


def test_gameboy_dma_accel_matches_reference():
    accel_bus = _FakePPUBus()
    ref_bus = _FakePPUBus()
    accel_bus.wram = bytearray(0x2000)
    ref_bus.wram = bytearray(0x2000)
    for index in range(0xA0):
        accel_bus.wram[index] = (index * 3) & 0xFF
        ref_bus.wram[index] = (index * 3) & 0xFF

    def _bind_read8(bus):
        def _read8(addr: int) -> int:
            if 0xC000 <= addr < 0xE000:
                return bus.wram[addr - 0xC000]
            return 0xFF

        bus.read8 = _read8

    _bind_read8(accel_bus)
    _bind_read8(ref_bus)

    accel = GameBoyDMAController(accel_bus)
    reference = GameBoyDMAControllerReference(ref_bus)

    accel.start(0xC0)
    reference.start(0xC0)
    accel.run_cycles(0xA0 * 4)
    reference.run_cycles(0xA0 * 4)

    assert accel.active == reference.active
    assert accel_bus.oam == ref_bus.oam
    assert accel_bus.oam_accessible == ref_bus.oam_accessible
