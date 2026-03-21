from __future__ import annotations

from machines.gameboy import DMG


def _pixel_at_rgb24(packed: bytes, width: int, x: int, y: int) -> tuple[int, int, int]:
    offset = (y * width + x) * 3
    return (packed[offset], packed[offset + 1], packed[offset + 2])


def _make_test_rom(*, title: str = "SMTEST", cartridge_type: int = 0x00) -> bytes:
    rom_size = 0x10000 if cartridge_type in {0x01, 0x02, 0x03, 0x05, 0x06, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0xFF} else 0x8000
    rom = bytearray(rom_size)
    title_bytes = title.encode("ascii")[:16]
    rom[0x0134 : 0x0134 + len(title_bytes)] = title_bytes
    rom[0x0147] = cartridge_type
    rom[0x0148] = 0x01 if rom_size > 0x8000 else 0x00
    rom[0x0149] = 0x00
    return bytes(rom)


def test_gameboy_machine_exposes_expected_frame_geometry():
    machine = DMG(_make_test_rom())

    assert machine.frame_width == 160
    assert machine.frame_height == 144
    assert len(machine.framebuffer_rgb24) == 160 * 144 * 3
    assert machine.input_keymap_name == "gameboy"
    assert machine.input_tap_hold_frames == 2
    assert machine.input_quick_tap_max_frames == 1
    assert machine.bus.read8(0xFF00) == 0xCF
    assert machine.bus.read8(0xFF01) == 0x00
    assert machine.bus.read8(0xFF02) == 0x7E
    assert machine.bus.read8(0xFF04) == 0xAB
    assert machine.bus.read8(0xFF0F) == 0xE1
    assert machine.bus.read8(0xFF41) == 0x85


def test_gameboy_serial_registers_roundtrip_through_io_handlers():
    machine = DMG(_make_test_rom())

    machine.bus.write8(0xFF01, 0xA5)
    machine.bus.write8(0xFF02, 0x81)

    assert machine.bus.read8(0xFF01) == 0xA5
    assert machine.bus.read8(0xFF02) == 0xFF


def test_gameboy_apu_channel_1_can_generate_audio_samples():
    machine = DMG(_make_test_rom())

    machine.bus.write8(0xFF26, 0x80)
    machine.bus.write8(0xFF24, 0x77)
    machine.bus.write8(0xFF25, 0x11)
    machine.bus.write8(0xFF11, 0x80)
    machine.bus.write8(0xFF12, 0xF0)
    machine.bus.write8(0xFF13, 0x40)
    machine.bus.write8(0xFF14, 0x87)

    machine.apu.begin_frame()
    machine.apu.run_cycles(machine.TSTATES_PER_FRAME)
    samples = machine.apu.get_frame_samples()

    assert len(samples) > 0
    assert any(sample != 0 for sample in samples)


def test_gameboy_apu_channel_2_can_generate_audio_samples():
    machine = DMG(_make_test_rom())

    machine.bus.write8(0xFF26, 0x80)
    machine.bus.write8(0xFF24, 0x77)
    machine.bus.write8(0xFF25, 0x22)
    machine.bus.write8(0xFF16, 0x80)
    machine.bus.write8(0xFF17, 0xF0)
    machine.bus.write8(0xFF18, 0x40)
    machine.bus.write8(0xFF19, 0x87)

    machine.apu.begin_frame()
    machine.apu.run_cycles(machine.TSTATES_PER_FRAME)
    samples = machine.apu.get_frame_samples()

    assert len(samples) > 0
    assert any(sample != 0 for sample in samples)


def test_gameboy_apu_channel_4_can_generate_audio_samples():
    machine = DMG(_make_test_rom())

    machine.bus.write8(0xFF26, 0x80)
    machine.bus.write8(0xFF24, 0x77)
    machine.bus.write8(0xFF25, 0x88)
    machine.bus.write8(0xFF20, 0x00)
    machine.bus.write8(0xFF21, 0xF0)
    machine.bus.write8(0xFF22, 0x13)
    machine.bus.write8(0xFF23, 0x80)

    machine.apu.begin_frame()
    machine.apu.run_cycles(machine.TSTATES_PER_FRAME)
    samples = machine.apu.get_frame_samples()

    assert len(samples) > 0
    assert any(sample != 0 for sample in samples)


def test_gameboy_apu_channel_3_can_generate_audio_samples():
    machine = DMG(_make_test_rom())

    machine.bus.write8(0xFF26, 0x80)
    machine.bus.write8(0xFF24, 0x77)
    machine.bus.write8(0xFF25, 0x44)
    for offset in range(16):
        machine.bus.write8(0xFF30 + offset, 0x1F)
    machine.bus.write8(0xFF1A, 0x80)
    machine.bus.write8(0xFF1B, 0x00)
    machine.bus.write8(0xFF1C, 0x20)
    machine.bus.write8(0xFF1D, 0x40)
    machine.bus.write8(0xFF1E, 0x87)

    machine.apu.begin_frame()
    machine.apu.run_cycles(machine.TSTATES_PER_FRAME)
    samples = machine.apu.get_frame_samples()

    assert len(samples) > 0
    assert any(sample != 0 for sample in samples)


def test_gameboy_apu_envelope_changes_channel_volume_over_time():
    machine = DMG(_make_test_rom())

    machine.bus.write8(0xFF26, 0x80)
    machine.bus.write8(0xFF11, 0x80)
    machine.bus.write8(0xFF12, 0x12)
    machine.bus.write8(0xFF13, 0x40)
    machine.bus.write8(0xFF14, 0x87)
    initial_volume = machine.apu._ch1_volume

    machine.apu.run_cycles((machine.apu.CPU_CLOCK_HZ // machine.apu.FRAME_SEQUENCER_HZ) * 16)

    assert machine.apu._ch1_volume < initial_volume


def test_gameboy_apu_channel_1_sweep_updates_frequency():
    machine = DMG(_make_test_rom())

    machine.bus.write8(0xFF26, 0x80)
    machine.bus.write8(0xFF10, 0x11)
    machine.bus.write8(0xFF11, 0x80)
    machine.bus.write8(0xFF12, 0xF0)
    machine.bus.write8(0xFF13, 0x00)
    machine.bus.write8(0xFF14, 0x84)
    initial_frequency = machine.apu._ch1_frequency

    machine.apu.run_cycles((machine.apu.CPU_CLOCK_HZ // machine.apu.FRAME_SEQUENCER_HZ) * 3)

    assert machine.apu._ch1_frequency > initial_frequency


def test_gameboy_apu_channel_1_sweep_disables_on_trigger_overflow():
    machine = DMG(_make_test_rom())

    machine.bus.write8(0xFF26, 0x80)
    machine.bus.write8(0xFF10, 0x12)
    machine.bus.write8(0xFF11, 0x80)
    machine.bus.write8(0xFF12, 0xF0)
    machine.bus.write8(0xFF13, 0xFF)
    machine.bus.write8(0xFF14, 0x87)

    assert (machine.apu.read_nr52() & 0x01) == 0


def test_gameboy_apu_channel_4_length_counter_disables_noise():
    machine = DMG(_make_test_rom())

    machine.bus.write8(0xFF26, 0x80)
    machine.bus.write8(0xFF20, 0x3F)
    machine.bus.write8(0xFF21, 0xF0)
    machine.bus.write8(0xFF22, 0x13)
    machine.bus.write8(0xFF23, 0xC0)

    assert machine.apu.read_nr52() & 0x08
    machine.apu.run_cycles((machine.apu.CPU_CLOCK_HZ // machine.apu.FRAME_SEQUENCER_HZ) * 2)

    assert (machine.apu.read_nr52() & 0x08) == 0


def test_gameboy_apu_channel_3_length_counter_disables_wave_channel():
    machine = DMG(_make_test_rom())

    machine.bus.write8(0xFF26, 0x80)
    machine.bus.write8(0xFF1A, 0x80)
    machine.bus.write8(0xFF1B, 0xFF)
    machine.bus.write8(0xFF1C, 0x20)
    machine.bus.write8(0xFF1E, 0xC0)

    assert machine.apu.read_nr52() & 0x04
    machine.apu.run_cycles((machine.apu.CPU_CLOCK_HZ // machine.apu.FRAME_SEQUENCER_HZ) * 2)

    assert (machine.apu.read_nr52() & 0x04) == 0


def test_gameboy_apu_wave_ram_is_visible_through_io_handlers():
    machine = DMG(_make_test_rom())

    machine.bus.write8(0xFF30, 0xAB)
    machine.bus.write8(0xFF3F, 0xCD)

    assert machine.bus.read8(0xFF30) == 0xAB
    assert machine.bus.read8(0xFF3F) == 0xCD


def test_gameboy_cartridge_metadata_is_exposed_in_snapshot():
    machine = DMG(_make_test_rom(title="HELLO"))

    snap = machine.snapshot()

    assert snap["cartridge_title"] == "HELLO"
    assert snap["cartridge_type"] == "ROM_ONLY"


def test_gameboy_accepts_mbc1_cartridges():
    machine = DMG(_make_test_rom(title="MARIO", cartridge_type=0x01))

    snap = machine.snapshot()

    assert snap["cartridge_title"] == "MARIO"
    assert snap["cartridge_type"] == "MBC1"


def test_gameboy_accepts_mbc3_cartridges():
    machine = DMG(_make_test_rom(title="POKE", cartridge_type=0x13))

    snap = machine.snapshot()

    assert snap["cartridge_title"] == "POKE"
    assert snap["cartridge_type"] == "MBC3+RAM+BATTERY"


def test_gameboy_accepts_mbc2_cartridges():
    machine = DMG(_make_test_rom(title="KIRBY", cartridge_type=0x05))

    snap = machine.snapshot()

    assert snap["cartridge_title"] == "KIRBY"
    assert snap["cartridge_type"] == "MBC2"


def test_gameboy_accepts_mbc5_cartridges():
    machine = DMG(_make_test_rom(title="ZELDA", cartridge_type=0x1B))

    snap = machine.snapshot()

    assert snap["cartridge_title"] == "ZELDA"
    assert snap["cartridge_type"] == "MBC5+RAM+BATTERY"


def test_gameboy_accepts_huc1_cartridges():
    machine = DMG(_make_test_rom(title="HUC1TEST", cartridge_type=0xFF))

    snap = machine.snapshot()

    assert snap["cartridge_title"] == "HUC1TEST"
    assert snap["cartridge_type"] == "HuC1+RAM+BATTERY"


def test_gameboy_run_frame_advances_frame_counter():
    rom = bytearray(_make_test_rom())
    rom[0x0100:0x0102] = bytes([0x76, 0x00])  # HALT, NOP
    machine = DMG(bytes(rom))

    machine.run_frame()

    assert machine.frame_counter == 1
    assert machine.tstates == machine.TSTATES_PER_FRAME


def test_gameboy_run_frame_pushes_apu_audio_into_ring_buffer():
    machine = DMG(_make_test_rom())
    machine.bus.write8(0xFF26, 0x80)
    machine.bus.write8(0xFF24, 0x77)
    machine.bus.write8(0xFF25, 0x11)
    machine.bus.write8(0xFF11, 0x80)
    machine.bus.write8(0xFF12, 0xF0)
    machine.bus.write8(0xFF13, 0x40)
    machine.bus.write8(0xFF14, 0x87)

    machine.run_frame()

    assert machine.frame_counter == 1
    assert len(machine.get_audio_samples()) > 0
    assert any(sample != 0 for sample in machine.get_audio_samples())
    assert machine.get_audio_buffered_samples() > 0


def test_gameboy_huc1_synthetic_rom_runs_multiple_frames():
    rom = bytearray(_make_test_rom(title="HUC1RUN", cartridge_type=0xFF))
    rom[0x0100:0x0108] = bytes(
        [
            0x3E, 0x02,        # LD A,02h
            0xEA, 0x00, 0x20,  # LD (2000h),A
            0xC3, 0x00, 0x01,  # JP 0100h
        ]
    )
    machine = DMG(bytes(rom))

    for _ in range(3):
        machine.run_frame()

    snap = machine.snapshot()

    assert snap["cartridge_title"] == "HUC1RUN"
    assert snap["cartridge_type"] == "HuC1+RAM+BATTERY"
    assert machine.frame_counter == 3
    assert machine.cpu.halted is False


def test_gameboy_ppu_tracks_ly_during_frame():
    machine = DMG(_make_test_rom())

    machine.ppu.begin_frame()
    machine.ppu.run_until(456 * 10 + 12)

    assert machine.ppu.read_ly() == 10
    assert machine.ppu.read_stat() & 0x03 in {0, 2, 3}


def test_gameboy_ppu_requests_vblank_interrupt_on_entry():
    machine = DMG(_make_test_rom())

    machine.ppu.begin_frame()
    machine.ppu.run_until(456 * 143 + 455)
    machine.interrupts.interrupt_flags = 0
    machine.ppu.run_until(456 * 144)

    assert machine.interrupts.interrupt_flags & 0x01


def test_gameboy_ppu_requests_lcd_stat_interrupt_for_lyc_match_when_enabled():
    machine = DMG(_make_test_rom())
    machine.ppu.write_stat(machine.ppu.read_stat() | 0x40)
    machine.ppu.write_lyc(5)
    machine.interrupts.interrupt_flags = 0

    machine.ppu.begin_frame()
    machine.ppu.run_until(456 * 5)

    assert machine.interrupts.interrupt_flags & 0x02


def test_gameboy_ppu_keeps_mode_transition_interrupts_when_run_until_skips_ahead():
    machine = DMG(_make_test_rom())
    machine.ppu.write_stat(machine.ppu.read_stat() | 0x08)
    machine.interrupts.interrupt_flags = 0

    machine.ppu.begin_frame()
    machine.ppu.run_until(300)

    assert machine.ppu.read_stat() & 0x03 == 0
    assert machine.interrupts.interrupt_flags & 0x02


def test_gameboy_ppu_requests_mode_1_stat_interrupt_on_vblank_entry():
    machine = DMG(_make_test_rom())
    machine.ppu.write_stat(machine.ppu.read_stat() | 0x10)
    machine.interrupts.interrupt_flags = 0

    machine.ppu.begin_frame()
    machine.ppu.run_until(456 * 144)

    assert machine.ppu.read_stat() & 0x03 == 1
    assert machine.interrupts.interrupt_flags & 0x02
    assert machine.interrupts.interrupt_flags & 0x01


def test_gameboy_ppu_blocks_oam_access_during_mode_2():
    machine = DMG(_make_test_rom())
    machine.bus.oam[0] = 0x12

    machine.ppu.begin_frame()
    machine.ppu.run_until(0)

    assert machine.ppu.read_stat() & 0x03 == 2
    assert machine.bus.read8(0xFE00) == 0xFF
    machine.bus.write8(0xFE00, 0x34)
    assert machine.bus.oam[0] == 0x12


def test_gameboy_ppu_blocks_vram_and_oam_access_during_mode_3():
    machine = DMG(_make_test_rom())
    machine.bus.vram[0] = 0x56
    machine.bus.oam[0] = 0x78

    machine.ppu.begin_frame()
    machine.ppu.run_until(100)

    assert machine.ppu.read_stat() & 0x03 == 3
    assert machine.bus.read8(0x8000) == 0xFF
    assert machine.bus.read8(0xFE00) == 0xFF
    machine.bus.write8(0x8000, 0x9A)
    machine.bus.write8(0xFE00, 0xBC)
    assert machine.bus.vram[0] == 0x56
    assert machine.bus.oam[0] == 0x78


def test_gameboy_ppu_restores_vram_and_oam_access_in_vblank():
    machine = DMG(_make_test_rom())

    machine.ppu.begin_frame()
    machine.ppu.run_until(456 * 144)

    assert machine.ppu.read_stat() & 0x03 == 1
    machine.bus.write8(0x8000, 0x9A)
    machine.bus.write8(0xFE00, 0xBC)
    assert machine.bus.read8(0x8000) == 0x9A
    assert machine.bus.read8(0xFE00) == 0xBC


def test_gameboy_timer_div_increments_with_cycles():
    machine = DMG(_make_test_rom())
    machine.timer.write_div(0x00)

    machine.timer.run_cycles(256)

    assert machine.timer.read_div() == 0x01


def test_gameboy_timer_increments_tima_when_enabled():
    machine = DMG(_make_test_rom())
    machine.timer.write_tac(0x05)

    machine.timer.run_cycles(16)

    assert machine.timer.read_tima() == 0x01


def test_gameboy_timer_reloads_tma_and_requests_interrupt_on_overflow():
    machine = DMG(_make_test_rom())
    machine.interrupts.interrupt_flags = 0
    machine.timer.write_tma(0xAB)
    machine.timer.write_tima(0xFF)
    machine.timer.write_tac(0x05)

    machine.timer.run_cycles(16)

    assert machine.timer.read_tima() == 0xAB
    assert machine.interrupts.interrupt_flags & 0x04


def test_gameboy_ppu_renders_background_tile_from_vram():
    machine = DMG(_make_test_rom())
    machine.ppu.write_bgp(0xE4)
    machine.bus.vram[0x1800] = 0x00

    for row in range(8):
        machine.bus.vram[row * 2] = 0xAA
        machine.bus.vram[row * 2 + 1] = 0x00

    packed = machine.render_frame()

    assert _pixel_at_rgb24(packed, machine.frame_width, 0, 0) == machine.ppu.PALETTE[1]
    assert _pixel_at_rgb24(packed, machine.frame_width, 1, 0) == machine.ppu.PALETTE[0]


def test_gameboy_ppu_applies_scx_scroll_to_background():
    machine = DMG(_make_test_rom())
    machine.ppu.write_bgp(0xE4)
    machine.ppu.write_scx(8)
    machine.bus.vram[0x1800] = 0x00
    machine.bus.vram[0x1801] = 0x01

    for row in range(8):
        machine.bus.vram[row * 2] = 0x00
        machine.bus.vram[row * 2 + 1] = 0x00

    tile1 = 16
    for row in range(8):
        machine.bus.vram[tile1 + row * 2] = 0xFF
        machine.bus.vram[tile1 + row * 2 + 1] = 0x00

    packed = machine.render_frame()

    assert _pixel_at_rgb24(packed, machine.frame_width, 0, 0) == machine.ppu.PALETTE[1]


def test_gameboy_ppu_applies_scy_scroll_to_background():
    machine = DMG(_make_test_rom())
    machine.ppu.write_bgp(0xE4)
    machine.ppu.write_scy(8)
    machine.bus.vram[0x1800] = 0x00
    machine.bus.vram[0x1820] = 0x01

    for row in range(8):
        machine.bus.vram[row * 2] = 0x00
        machine.bus.vram[row * 2 + 1] = 0x00

    tile1 = 16
    for row in range(8):
        machine.bus.vram[tile1 + row * 2] = 0xFF
        machine.bus.vram[tile1 + row * 2 + 1] = 0x00

    packed = machine.render_frame()

    assert _pixel_at_rgb24(packed, machine.frame_width, 0, 0) == machine.ppu.PALETTE[1]


def test_gameboy_ppu_latches_scroll_per_scanline():
    machine = DMG(_make_test_rom())
    machine.ppu.write_bgp(0xE4)
    machine.bus.vram[0x1800] = 0x00
    machine.bus.vram[0x1801] = 0x01

    for row in range(8):
        machine.bus.vram[row * 2] = 0x00
        machine.bus.vram[row * 2 + 1] = 0x00

    tile1 = 16
    for row in range(8):
        machine.bus.vram[tile1 + row * 2] = 0xFF
        machine.bus.vram[tile1 + row * 2 + 1] = 0x00

    machine.ppu.begin_frame()
    machine.ppu.write_scx(0)
    machine.ppu.run_until(79)
    machine.ppu.write_scx(8)
    machine.ppu.run_until(456 + 79)
    machine.ppu.write_scx(0)
    machine.ppu.run_until(456 + 80)

    packed = machine.ppu.render_frame()

    assert _pixel_at_rgb24(packed, machine.frame_width, 0, 0) == machine.ppu.PALETTE[1]
    assert _pixel_at_rgb24(packed, machine.frame_width, 0, 1) == machine.ppu.PALETTE[0]


def test_gameboy_ppu_window_overrides_background_when_enabled():
    machine = DMG(_make_test_rom())
    machine.ppu.write_bgp(0xE4)
    machine.ppu.write_lcdc(machine.ppu.read_lcdc() | 0x20)
    machine.ppu.write_wx(7)
    machine.ppu.write_wy(0)

    machine.bus.vram[0x1800] = 0x01

    for row in range(8):
        machine.bus.vram[row * 2] = 0x00
        machine.bus.vram[row * 2 + 1] = 0x00

    tile1 = 16
    for row in range(8):
        machine.bus.vram[tile1 + row * 2] = 0xFF
        machine.bus.vram[tile1 + row * 2 + 1] = 0x00

    packed = machine.render_frame()

    assert _pixel_at_rgb24(packed, machine.frame_width, 0, 0) == machine.ppu.PALETTE[1]


def test_gameboy_ppu_window_honors_negative_screen_x_when_wx_is_less_than_7():
    machine = DMG(_make_test_rom())
    machine.ppu.write_bgp(0xE4)
    machine.ppu.write_lcdc(machine.ppu.read_lcdc() | 0x20)
    machine.ppu.write_wx(0)
    machine.ppu.write_wy(0)

    machine.bus.vram[0x1800] = 0x00
    machine.bus.vram[0x1801] = 0x01

    for row in range(8):
        machine.bus.vram[row * 2] = 0x00
        machine.bus.vram[row * 2 + 1] = 0x00

    tile1 = 16
    for row in range(8):
        machine.bus.vram[tile1 + row * 2] = 0xFF
        machine.bus.vram[tile1 + row * 2 + 1] = 0x00

    packed = machine.render_frame()

    assert _pixel_at_rgb24(packed, machine.frame_width, 0, 0) == machine.ppu.PALETTE[0]
    assert _pixel_at_rgb24(packed, machine.frame_width, 1, 0) == machine.ppu.PALETTE[1]


def test_gameboy_ppu_uses_signed_tile_data_region_when_requested():
    machine = DMG(_make_test_rom())
    machine.ppu.write_bgp(0xE4)
    machine.ppu.write_lcdc(machine.ppu.read_lcdc() & ~0x10)
    machine.bus.vram[0x1800] = 0xFF

    tile_addr = 0x1000 - 16
    for row in range(8):
        machine.bus.vram[tile_addr + row * 2] = 0xFF
        machine.bus.vram[tile_addr + row * 2 + 1] = 0x00

    packed = machine.render_frame()

    assert _pixel_at_rgb24(packed, machine.frame_width, 0, 0) == machine.ppu.PALETTE[1]


def test_gameboy_ppu_renders_sprite_from_oam():
    machine = DMG(_make_test_rom())
    machine.ppu.write_bgp(0xFC)
    machine.ppu.write_obp0(0xE4)
    machine.ppu.write_lcdc(machine.ppu.read_lcdc() | 0x02)

    for row in range(8):
        machine.bus.vram[row * 2] = 0x00
        machine.bus.vram[row * 2 + 1] = 0x00

    tile1 = 16
    for row in range(8):
        machine.bus.vram[tile1 + row * 2] = 0xFF
        machine.bus.vram[tile1 + row * 2 + 1] = 0x00

    machine.bus.oam[0] = 16
    machine.bus.oam[1] = 8
    machine.bus.oam[2] = 1
    machine.bus.oam[3] = 0

    packed = machine.render_frame()

    assert _pixel_at_rgb24(packed, machine.frame_width, 0, 0) == machine.ppu.PALETTE[1]


def test_gameboy_ppu_renders_sprites_even_when_bg_is_disabled():
    machine = DMG(_make_test_rom())
    machine.ppu.write_bgp(0xFC)
    machine.ppu.write_obp0(0xE4)
    machine.ppu.write_lcdc((machine.ppu.read_lcdc() | 0x02) & ~0x01)

    tile1 = 16
    for row in range(8):
        machine.bus.vram[tile1 + row * 2] = 0xFF
        machine.bus.vram[tile1 + row * 2 + 1] = 0x00

    machine.bus.oam[0:4] = bytes([16, 8, 1, 0])

    packed = machine.render_frame()

    assert _pixel_at_rgb24(packed, machine.frame_width, 0, 0) == machine.ppu.PALETTE[1]


def test_gameboy_ppu_latches_bg_enable_per_scanline():
    machine = DMG(_make_test_rom())
    machine.ppu.write_bgp(0xE4)
    machine.bus.vram[0x1800] = 0x00
    machine.bus.vram[0x1820] = 0x00

    for row in range(8):
        machine.bus.vram[row * 2] = 0xFF
        machine.bus.vram[row * 2 + 1] = 0x00

    machine.ppu.begin_frame()
    machine.ppu.write_lcdc(machine.ppu.read_lcdc())
    machine.ppu.run_until(80)
    machine.ppu.write_lcdc(machine.ppu.read_lcdc() & ~0x01)
    machine.ppu.run_until(456 + 80)
    packed = machine.ppu.render_frame()

    assert _pixel_at_rgb24(packed, machine.frame_width, 0, 0) == machine.ppu.PALETTE[1]
    assert _pixel_at_rgb24(packed, machine.frame_width, 0, 1) == machine.ppu.PALETTE[0]


def test_gameboy_ppu_latches_background_palette_per_scanline():
    machine = DMG(_make_test_rom())
    machine.ppu.write_bgp(0xE4)
    machine.bus.vram[0x1800] = 0x00
    machine.bus.vram[0x1820] = 0x00

    for row in range(8):
        machine.bus.vram[row * 2] = 0xFF
        machine.bus.vram[row * 2 + 1] = 0x00

    machine.ppu.begin_frame()
    machine.ppu.write_bgp(0xE4)
    machine.ppu.run_until(80)
    machine.ppu.write_bgp(0x1B)
    machine.ppu.run_until(456 + 80)

    packed = machine.ppu.render_frame()

    assert _pixel_at_rgb24(packed, machine.frame_width, 0, 0) == machine.ppu.PALETTE[1]
    assert _pixel_at_rgb24(packed, machine.frame_width, 0, 1) == machine.ppu.PALETTE[2]


def test_gameboy_ppu_prefers_sprite_with_smaller_x_when_sprites_overlap():
    machine = DMG(_make_test_rom())
    machine.ppu.write_bgp(0xFC)
    machine.ppu.write_obp0(0xE4)
    machine.ppu.write_obp1(0xD8)
    machine.ppu.write_lcdc(machine.ppu.read_lcdc() | 0x02)

    tile1 = 16
    tile2 = 32
    for row in range(8):
        machine.bus.vram[tile1 + row * 2] = 0xFF
        machine.bus.vram[tile1 + row * 2 + 1] = 0x00
        machine.bus.vram[tile2 + row * 2] = 0x00
        machine.bus.vram[tile2 + row * 2 + 1] = 0xFF

    machine.bus.oam[0:4] = bytes([16, 12, 2, 0x10])
    machine.bus.oam[4:8] = bytes([16, 8, 1, 0x00])

    packed = machine.render_frame()

    assert _pixel_at_rgb24(packed, machine.frame_width, 4, 0) == machine.ppu.PALETTE[1]


def test_gameboy_ppu_limits_to_ten_sprites_per_line():
    machine = DMG(_make_test_rom())
    machine.ppu.write_obp0(0xE4)
    machine.ppu.write_lcdc(machine.ppu.read_lcdc() | 0x02)

    tile1 = 16
    for row in range(8):
        machine.bus.vram[tile1 + row * 2] = 0xFF
        machine.bus.vram[tile1 + row * 2 + 1] = 0x00

    for index in range(11):
        base = index * 4
        machine.bus.oam[base] = 16
        machine.bus.oam[base + 1] = 8 + index * 8
        machine.bus.oam[base + 2] = 1
        machine.bus.oam[base + 3] = 0

    packed = machine.render_frame()

    assert _pixel_at_rgb24(packed, machine.frame_width, 0, 0) == machine.ppu.PALETTE[1]
    assert _pixel_at_rgb24(packed, machine.frame_width, 72, 0) == machine.ppu.PALETTE[1]
    assert _pixel_at_rgb24(packed, machine.frame_width, 80, 0) == machine.ppu.PALETTE[0]


def test_gameboy_sprite_priority_behind_bg_uses_bg_color_id_not_rgb():
    machine = DMG(_make_test_rom())
    machine.ppu.write_bgp(0xE4)
    machine.ppu.write_obp0(0xE4)
    machine.ppu.write_lcdc(machine.ppu.read_lcdc() | 0x02)

    machine.bus.vram[0x1800] = 0x00
    for row in range(8):
        machine.bus.vram[row * 2] = 0xFF
        machine.bus.vram[row * 2 + 1] = 0x00

    tile1 = 16
    for row in range(8):
        machine.bus.vram[tile1 + row * 2] = 0xFF
        machine.bus.vram[tile1 + row * 2 + 1] = 0x00

    machine.bus.oam[0:4] = bytes([16, 8, 1, 0x80])

    packed = machine.render_frame()

    assert _pixel_at_rgb24(packed, machine.frame_width, 0, 0) == machine.ppu.PALETTE[1]


def test_gameboy_joypad_requests_interrupt_on_new_press():
    machine = DMG(_make_test_rom())
    machine.interrupts.interrupt_flags = 0
    machine.joypad.write_p1(0x10)

    machine.joypad.press(1, 0)

    assert machine.interrupts.interrupt_flags & 0x10


def test_gameboy_joypad_read_reflects_selected_direction_group():
    machine = DMG(_make_test_rom())
    machine.joypad.write_p1(0x20)
    machine.joypad.press(0, 0)

    assert machine.joypad.read_p1() & 0x01 == 0


def test_gameboy_joypad_reads_button_group_when_selected():
    machine = DMG(_make_test_rom())
    machine.joypad.write_p1(0x10)
    machine.joypad.press(1, 0)

    assert machine.joypad.read_p1() & 0x01 == 0


def test_gameboy_dma_progressively_copies_bytes_into_oam():
    machine = DMG(_make_test_rom())
    for i in range(0xA0):
        machine.bus.write8(0xC000 + i, i)

    machine._write_dma(0xC0)
    assert machine.bus.read8(0xFE00) == 0xFF

    machine._run_dma(4)

    assert machine.bus.oam[0] == 0
    assert machine.bus.oam[1] == 0
    assert machine.bus.read8(0xFE00) == 0xFF

    machine._run_dma((0xA0 - 1) * 4)

    assert list(machine.bus.oam[:16]) == list(range(16))
    assert machine.bus.read8(0xFE00) == 0
