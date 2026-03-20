from __future__ import annotations

"""Minimal Amstrad CPC 464 machine model on top of the shared Z80 core.

This first cut focuses on the parts that define the CPC identity at the memory
map level: 64 KB of RAM plus a lower and upper ROM overlay. Video, keyboard,
Gate Array and CRTC timing are intentionally simplified so the project can
grow the machine incrementally without blocking on full hardware accuracy.
"""

import os
from array import array

from cpu.z80 import MemoryDevice, PythonPortHandler, RAMBlock, ROMBlock
from devices import AY38912, CPCCassetteTape, CPCGateArray, CPCVideo, HD6845, Intel8255
from machines.frame_runner import ScanlineFrameRunner
from machines.z80.base import Z80MachineBase
from video import get_display_profile


class CPCMemoryMap(MemoryDevice):
    """Expose CPC RAM plus ROM overlays through the generic bus device API."""

    def __init__(self, machine: "CPC464"):
        self.machine = machine

    def read(self, addr):
        if 0x0000 <= addr < 0x4000 and self.machine.lower_rom_enabled:
            return self.machine.lower_rom.peek(addr)

        if 0xC000 <= addr <= 0xFFFF and self.machine.upper_rom_enabled:
            return self.machine.upper_rom.peek(addr - 0xC000)

        return self.machine.ram.peek(addr)

    def write(self, addr, value):
        # On the CPC the RAM is always physically present, even where ROM is
        # currently visible. Writes therefore always land in RAM underneath.
        self.machine.ram.load(addr, bytes([value & 0xFF]))


class CPC464(Z80MachineBase):
    """Amstrad CPC 464 with a first-pass memory and execution model.

    Current scope:
    - Z80 execution
    - 64 KB RAM
    - lower and upper ROM overlays
    - first-pass rgb24 frame with active area plus border

    Deferred for later sessions:
    - cycle-accurate Gate Array fetch/timing
    - more faithful CRTC timing and blanking
    - cassette support
    """

    RAM_SIZE = 0x10000
    ROM_SIZE = 0x4000
    TSTATES_PER_FRAME = 79872
    SCANLINES_PER_FRAME = 312
    TSTATES_PER_LINE = TSTATES_PER_FRAME // SCANLINES_PER_FRAME
    INTERRUPT_PERIOD_LINES = 52
    VSYNC_LINES = 2
    # A full CPC frame is larger than the active text/bitmap area. Using a
    # fixed frame with visible border keeps the machine looking more like a
    # CPC now, while still avoiding a full timing-accurate raster model.
    FRAME_WIDTH = 384
    FRAME_HEIGHT = 272
    KEYBOARD_LINES = 10
    KEYBOARD_BITS = 8
    FRAMES_PER_SECOND = 50
    PSG_CLOCK_HZ = 1_000_000
    # The default firmware register set positions the display a little before
    # the sync point. These offsets keep the first-pass raster aligned with
    # what software expects while still letting register changes move it.
    HORIZONTAL_DISPLAY_OFFSET_CHARS = 4
    VERTICAL_DISPLAY_OFFSET_ROWS = 0
    DEFAULT_HORIZONTAL_SYNC_POSITION = HD6845.DEFAULT_REGISTERS[2]
    DEFAULT_VERTICAL_SYNC_POSITION = HD6845.DEFAULT_REGISTERS[7]
    input_keymap_name = "cpc"
    _BLANK_PIXEL = (0, 0, 0)

    def __init__(
        self,
        rom_data: bytes | None = None,
        *,
        basic_rom_data: bytes | None = None,
        tape_data: bytes | None = None,
        fast_tape: bool | None = None,
        audio_sample_rate: int = 44100,
        display_profile: str = "default",
    ):
        super().__init__(audio_sample_rate=audio_sample_rate)
        self.display_profile_name = display_profile
        self.display_profile = get_display_profile(display_profile)
        self.frame_width = self.display_profile.cpc_frame_width or self.FRAME_WIDTH
        self.frame_height = self.display_profile.cpc_frame_height or self.FRAME_HEIGHT

        self.lower_rom = ROMBlock(self.ROM_SIZE)
        self.upper_rom = ROMBlock(self.ROM_SIZE)
        self.ram = RAMBlock(self.RAM_SIZE)

        if rom_data is not None:
            self.lower_rom.load_bytes(rom_data)
        if basic_rom_data is not None:
            self.upper_rom.load_bytes(basic_rom_data)

        self.lower_rom_enabled = True
        self.upper_rom_enabled = basic_rom_data is not None
        self._has_upper_rom = basic_rom_data is not None
        self.samples_per_frame = int(round(audio_sample_rate / self.FRAMES_PER_SECOND))

        self.memory_map = CPCMemoryMap(self)
        self.bus.map_device(0x0000, 0x10000, self.memory_map)
        self.gate_array = CPCGateArray(self)
        self.crtc = HD6845()
        self.ppi = Intel8255(self)
        self.video = CPCVideo(self)
        self.keyboard_lines = [0xFF] * self.KEYBOARD_LINES
        self.last_keyboard_line_read = 0xFF
        self.interrupt_counter = 0
        self.vsync_active = False
        self.current_scanline = 0
        self.current_crtc_row = 0
        self.current_char_row = 0
        self.current_raster_address = 0
        self.frame_display_start_address = self.crtc.display_start_address
        self.frame_gate_mode = self.gate_array.mode
        self.frame_border_hardware_color = self.gate_array.border_hardware_color
        self.line_display_start_addresses = [self.crtc.display_start_address] * self.SCANLINES_PER_FRAME
        self.line_gate_modes = [self.gate_array.mode] * self.SCANLINES_PER_FRAME
        self.line_border_colours = [self.gate_array.border_hardware_color] * self.SCANLINES_PER_FRAME
        self.psg = AY38912(
            clock_hz=self.PSG_CLOCK_HZ,
            sample_rate=audio_sample_rate,
            port_a_read=self._read_psg_port_a,
            # CPC firmware leaves PSG register 7 with port A configured as an
            # output during parts of the boot flow, but keyboard reads still
            # need to observe the external matrix wired to the port pins.
            port_a_read_through_output=True,
        )
        self._configure_psg_defaults()
        if fast_tape is None:
            fast_tape = os.environ.get("MULTIEMU_CPC_TAPE_FAST", "0").lower() not in {"0", "false", "no", "off"}
        self.fast_tape = bool(fast_tape)
        self.cassette = (
            CPCCassetteTape.from_cdt_bytes(tape_data, fast=self.fast_tape)
            if tape_data is not None
            else None
        )
        self.audio_samples = array("h", [0] * self.samples_per_frame)
        self._frame_audio = array("h")
        self._audio_rendered_samples = 0
        self._device_tstates = 0
        self._sound_trace_path = os.environ.get("MULTIEMU_CPC_SOUND_TRACE")
        if self._sound_trace_path:
            with open(self._sound_trace_path, "w", encoding="utf-8") as trace:
                trace.write("# CPC sound trace\n")

        # The CPC I/O space is only partially decoded. Using the same handler
        # for all low-byte values keeps the current bus abstraction workable
        # while still letting the callback inspect the full 16-bit port.
        for port_low in range(256):
            self.bus.set_port_handler(
                port_low,
                PythonPortHandler(self._port_read, self._port_write),
            )

        self.framebuffer_rgb24 = self.video.framebuffer_rgb24
        self._frame_runner = ScanlineFrameRunner(self.SCANLINES_PER_FRAME, self.TSTATES_PER_LINE)

    @property
    def framebuffer_rgb24(self):
        if hasattr(self, "video"):
            return self.video.framebuffer_rgb24
        return getattr(self, "_framebuffer_rgb24", None)

    @framebuffer_rgb24.setter
    def framebuffer_rgb24(self, value):
        if hasattr(self, "video"):
            self.video.framebuffer_rgb24 = value
            return
        self._framebuffer_rgb24 = value

    def reset(self):
        """Reset CPU and restore the default ROM visibility state."""

        super().reset()
        self.lower_rom_enabled = True
        self.upper_rom_enabled = self._has_upper_rom
        self.gate_array.reset()
        self.crtc.reset()
        self.psg.reset()
        self.ppi.reset()
        self.keyboard_lines = [0xFF] * self.KEYBOARD_LINES
        self.last_keyboard_line_read = 0xFF
        self.interrupt_counter = 0
        self.vsync_active = False
        self.current_scanline = 0
        self.current_crtc_row = 0
        self.current_char_row = 0
        self.current_raster_address = 0
        self.frame_display_start_address = self.crtc.display_start_address
        self.frame_gate_mode = self.gate_array.mode
        self.frame_border_hardware_color = self.gate_array.border_hardware_color
        self.line_display_start_addresses = [self.crtc.display_start_address] * self.SCANLINES_PER_FRAME
        self.line_gate_modes = [self.gate_array.mode] * self.SCANLINES_PER_FRAME
        self.line_border_colours = [self.gate_array.border_hardware_color] * self.SCANLINES_PER_FRAME
        self._configure_psg_defaults()
        if self.cassette is not None:
            self.cassette.reset()
        self.audio_samples = array("h", [0] * self.samples_per_frame)
        self._frame_audio = array("h")
        self._audio_rendered_samples = 0
        self._device_tstates = 0
        self.video.reset()
        self.video.render_frame()

    def set_rom_configuration(
        self,
        *,
        lower_rom_enabled: bool | None = None,
        upper_rom_enabled: bool | None = None,
    ) -> None:
        """Control which ROM overlays are currently visible to the CPU."""

        if lower_rom_enabled is not None:
            self.lower_rom_enabled = bool(lower_rom_enabled)

        if upper_rom_enabled is not None:
            self.upper_rom_enabled = bool(upper_rom_enabled) and self._has_upper_rom

    def _begin_frame(self) -> None:
        self.frame_tstates = 0
        self._frame_audio = array("h")
        self._audio_rendered_samples = 0
        self._device_tstates = 0

        total_scanlines = self.video._get_frame_scanline_count()
        self.frame_display_start_address = self.crtc.display_start_address
        self.frame_gate_mode = self.gate_array.mode
        self.frame_border_hardware_color = self.gate_array.border_hardware_color
        self.line_display_start_addresses = [self.crtc.display_start_address] * total_scanlines
        self.line_gate_modes = [self.gate_array.mode] * total_scanlines
        self.line_border_colours = [self.gate_array.border_hardware_color] * total_scanlines

    def _begin_scanline(self, scanline: int) -> None:
        self.current_scanline = scanline
        self.vsync_active = self.video._is_vsync_scanline(scanline)
        self.gate_array.begin_scanline(self.vsync_active)
        raster_pos = self.video._decode_crtc_scanline(scanline)
        if raster_pos is None:
            self.current_crtc_row = -1
            self.current_char_row = -1
            self.current_raster_address = -1
        else:
            self.current_crtc_row, self.current_raster_address = raster_pos

        display_pos = self.video._decode_display_scanline(scanline)
        if display_pos is None:
            self.current_char_row = -1
        else:
            self.current_char_row, self.current_raster_address = display_pos

        if self.gate_array.pending_interrupt and self.cpu.interrupts_enabled():
            self.gate_array.pending_interrupt = False
            self.cpu.interrupt()
            self.gate_array.acknowledge_interrupt()
            self.interrupt_counter += 1
            self._trace_sound("irq", scanline=scanline, delivered=1, count=self.interrupt_counter)

        self.line_display_start_addresses[scanline] = self.crtc.display_start_address
        self.line_gate_modes[scanline] = self.gate_array.mode
        self.line_border_colours[scanline] = self.gate_array.border_hardware_color

    def _end_scanline(self, scanline: int) -> None:
        del scanline
        self.gate_array.end_scanline()

    def _after_scanline_cpu(self, frame_tstates: int, scanline: int) -> None:
        del scanline
        self._run_devices_until(frame_tstates)

    def _finish_frame(self) -> None:
        self.vsync_active = False
        self.video.render_frame()
        self.audio_samples = self._render_audio_frame()
        self.audio_ring.write(self.audio_samples)
        self.frame_counter += 1

    def run_frame(self) -> int:
        """Advance one CPC frame worth of CPU time."""

        self._frame_runner.run(
            self,
            self.cpu.run_cycles,
            self._begin_frame,
            self._begin_scanline,
            self._after_scanline_cpu,
            self._end_scanline,
            self._finish_frame,
        )
        return self.tstates

    def render_frame(self):
        """Render the current CPC frame and return canonical rgb24 bytes."""

        return self.video.render_frame()

    def _run_devices_until(self, tstates: int):
        """Advance timed peripherals up to the current frame tstate."""

        delta_tstates = max(0, tstates - self._device_tstates)
        target_samples = (max(0, min(self.TSTATES_PER_FRAME, tstates)) * self.samples_per_frame) // self.TSTATES_PER_FRAME
        delta_samples = target_samples - self._audio_rendered_samples
        if delta_samples > 0:
            self._frame_audio.extend(self.psg.render_samples(delta_samples))
            self._audio_rendered_samples = target_samples
        if self.cassette is not None and delta_tstates > 0:
            self.cassette.run_cycles(delta_tstates)
        self._device_tstates = tstates

    def load_lower_rom(self, data: bytes):
        """Load the CPC lower ROM image."""

        self.lower_rom.load_bytes(data)

    def load_upper_rom(self, data: bytes):
        """Load the CPC upper ROM image and expose it by default."""

        self.upper_rom.load_bytes(data)
        self._has_upper_rom = True
        self.upper_rom_enabled = True

    def poke(self, addr: int, value: int):
        """Write to CPC RAM, including areas currently hidden by ROM."""

        if not 0 <= addr <= 0xFFFF:
            raise ValueError("dirección fuera de rango")
        self.ram.load(addr, bytes([value & 0xFF]))

    def peek(self, addr: int) -> int:
        """Read the byte currently visible to the CPU at ``addr``."""

        if not 0 <= addr <= 0xFFFF:
            raise ValueError("dirección fuera de rango")
        return self.memory_map.read(addr)

    def load_ram(self, addr: int, data: bytes):
        """Load raw data into CPC RAM regardless of current ROM visibility."""

        if not (0 <= addr <= 0xFFFF) or addr + len(data) > self.RAM_SIZE:
            raise ValueError("el rango debe caer dentro de la RAM 0x0000-0xFFFF")
        self.ram.load(addr, data)

    def snapshot(self) -> dict:
        """Return CPU state plus the current ROM visibility flags."""

        snap = self.cpu.snapshot()
        snap["tstates"] = self.tstates
        snap["frame_counter"] = self.frame_counter
        snap["frame_tstates"] = self.frame_tstates
        snap["lower_rom_enabled"] = self.lower_rom_enabled
        snap["upper_rom_enabled"] = self.upper_rom_enabled
        snap["ga_mode"] = self.gate_array.mode
        snap["ga_border_hardware_color"] = self.gate_array.border_hardware_color
        snap["ga_selected_pen"] = self.gate_array.selected_pen
        snap["crtc_selected_register"] = self.crtc.selected_register
        snap["crtc_display_start"] = self.crtc.display_start_address
        snap["ppi_port_c"] = self.ppi.port_c_latch
        snap["ppi_control"] = self.ppi.control
        snap["ppi_last_port_a_read"] = self.ppi.last_port_a_read
        snap["ppi_last_port_a_write"] = self.ppi.last_port_a_write
        snap["ppi_last_control_write"] = self.ppi.last_control_write
        snap["psg_selected_register"] = self.psg.selected_register
        snap["psg_last_read_value"] = self.psg.last_read_value
        snap["keyboard_line_selected"] = self.ppi.selected_keyboard_line
        snap["keyboard_last_line_read"] = self.last_keyboard_line_read
        snap["interrupt_counter"] = self.interrupt_counter
        snap["vsync_active"] = self.vsync_active
        snap["current_scanline"] = self.current_scanline
        snap["current_crtc_row"] = self.current_crtc_row
        snap["current_char_row"] = self.current_char_row
        snap["current_raster_address"] = self.current_raster_address
        return snap

    def clear_input_state(self):
        """Release all CPC keyboard lines before the frontend applies a frame state."""

        self.keyboard_lines = [0xFF] * self.KEYBOARD_LINES

    def _press_key(self, line: int, bit: int):
        self.keyboard_lines[line] &= ~(1 << bit)
        self.keyboard_lines[line] &= 0xFF

    def _release_key(self, line: int, bit: int):
        self.keyboard_lines[line] |= 1 << bit
        self.keyboard_lines[line] &= 0xFF

    def handle_input_event(self, event):
        """Apply local frontend key events to the CPC keyboard matrix."""

        if event.kind != "key_matrix":
            raise ValueError(f"tipo de input no soportado: {event.kind}")

        line = int(event.control_a)
        bit = int(event.control_b)
        if not (0 <= line < self.KEYBOARD_LINES and 0 <= bit < self.KEYBOARD_BITS):
            raise ValueError(f"posición de tecla fuera de rango: {(line, bit)!r}")

        if event.active:
            self._press_key(line, bit)
        else:
            self._release_key(line, bit)

    def read_keyboard_line(self, line: int) -> int:
        """Return the current CPC keyboard line as active-low bits."""

        self.last_keyboard_line_read = line
        if 0 <= line < self.KEYBOARD_LINES:
            return self.keyboard_lines[line]
        return 0xFF

    def _read_psg_port_a(self) -> int:
        """Expose the selected CPC keyboard line on PSG port A."""

        return self.read_keyboard_line(self.ppi.selected_keyboard_line)

    def _configure_psg_defaults(self) -> None:
        """Apply CPC-specific PSG defaults after chip reset.

        CPC firmware expects PSG port A to behave as keyboard input. Keeping
        that as the machine-level default avoids requiring every boot path to
        reprogram register 7 before keyboard reads become meaningful.
        """

        self.psg.registers[7] |= 0x40

    def _port_read(self, port: int) -> int:
        """Return the default floating bus value for unimplemented I/O reads."""

        if (port & 0x0800) == 0:
            ppi_function = (port >> 8) & 0x03
            if ppi_function == 0x00:
                return self.ppi.read_port_a()
            if ppi_function == 0x01:
                return self.ppi.read_port_b()
            if ppi_function == 0x02:
                return self.ppi.read_port_c()
        return 0xFF

    def _port_write(self, port: int, value: int) -> None:
        """Dispatch CPC I/O writes to the Gate Array or future devices."""

        if (port & 0xC000) == 0x4000:
            self.gate_array.write(value)
            return

        if (port & 0xC000) == 0x8000:
            crtc_port = (port >> 8) & 0x03
            if crtc_port == 0x00:
                self.crtc.select_register(value)
            elif crtc_port == 0x01:
                self.crtc.write_selected(value)
                if self.crtc.selected_register in (12, 13):
                    self.frame_display_start_address = self.crtc.display_start_address
            return

        if (port & 0x0800) == 0:
            ppi_function = (port >> 8) & 0x03
            if ppi_function == 0x00:
                self.ppi.write_port_a(value)
            elif ppi_function == 0x01:
                self.ppi.write_port_b(value)
            elif ppi_function == 0x02:
                self.ppi.write_port_c(value)
            else:
                self.ppi.write_control(value)

    def _apply_psg_bus_control(self) -> None:
        """Apply the current PPI->PSG bus control state."""

        if self.ppi.psg_function == 0b11:
            self.psg.select_register(self.ppi.port_a_latch)
            self._trace_sound("psg_select", register=self.ppi.port_a_latch & 0x0F)
        elif self.ppi.psg_function == 0b10:
            self.psg.write_selected(self.ppi.port_a_latch)
            self._trace_sound(
                "psg_write",
                register=self.psg.selected_register,
                value=self.ppi.port_a_latch & 0xFF,
            )

    def _apply_tape_port_c(self) -> None:
        if self.cassette is None:
            return
        # Port C bit 4 controls tape motor on the CPC.
        self.cassette.set_motor(bool(self.ppi.port_c_latch & 0x10))

    def read_cassette_input(self) -> int:
        if self.cassette is None:
            return 0
        return self.cassette.level

    def toggle_tape_play_pause(self) -> bool:
        if self.cassette is None:
            return False
        return self.cassette.toggle_play_pause()

    def _render_audio_frame(self) -> array:
        """Render one CPC frame worth of AY audio into the shared ring buffer."""

        remaining = self.samples_per_frame - self._audio_rendered_samples
        if remaining > 0:
            self._frame_audio.extend(self.psg.render_samples(remaining))
            self._audio_rendered_samples = self.samples_per_frame
        elif remaining < 0:
            del self._frame_audio[self.samples_per_frame:]
            self._audio_rendered_samples = self.samples_per_frame
        frame_audio = array("h", self._frame_audio)
        if self._sound_trace_path and frame_audio:
            peak = 0
            for sample in frame_audio:
                amplitude = -sample if sample < 0 else sample
                if amplitude > peak:
                    peak = amplitude
            self._trace_sound("audio_frame", peak=peak)
        return frame_audio

    def _trace_sound(self, event: str, **fields) -> None:
        path = self._sound_trace_path
        if not path:
            return
        parts = [
            f"frame={self.frame_counter}",
            f"t={self.frame_tstates}",
            f"event={event}",
        ]
        for key, value in fields.items():
            parts.append(f"{key}={value}")
        with open(path, "a", encoding="utf-8") as trace:
            trace.write(" ".join(parts) + "\n")
