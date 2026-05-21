from __future__ import annotations

from array import array

from cpu.z80 import MemoryDevice, RAMBlock, ROMBlock, PythonPortHandler, Z80Bus, Z80Core
from chipsets import AY38912, Spectrum48KULA
from devices import SpectrumCassetteTape
from frontend.input_events import (
    InputEvent,
    JOYSTICK_DOWN,
    JOYSTICK_FIRE,
    JOYSTICK_FIRE_2,
    JOYSTICK_LEFT,
    JOYSTICK_RIGHT,
    JOYSTICK_UP,
)
from machines.base import BaseMachine
from machines.common import build_debug_devices, restore_fixed_length_list
from machines.frame_runner import SteppedFrameRunner
from machines.z80.spectrum_snapshot import apply_z80_snapshot
from video import get_display_profile


class SpectrumBase(BaseMachine):
    """Common ZX Spectrum machine behavior shared across memory variants."""

    ROM_SIZE = 0x4000
    RAM_SIZE = 0x4000
    RAM_BASE = 0x4000
    TSTATES_PER_FRAME = 69888
    FRAMES_PER_SECOND = 50
    input_keymap_name = "spectrum"
    input_gamepad_map_name = "spectrum"
    input_joystick_count = 2
    JOYSTICK_KEY_BINDINGS = (
        {
            JOYSTICK_LEFT: (4, 4),   # 6
            JOYSTICK_DOWN: (4, 3),   # 7
            JOYSTICK_UP: (4, 2),     # 8
            JOYSTICK_RIGHT: (4, 1),  # 9
            JOYSTICK_FIRE: (4, 0),   # 0
            JOYSTICK_FIRE_2: (6, 0), # Enter
        },
        {
            JOYSTICK_LEFT: (3, 0),   # 1
            JOYSTICK_DOWN: (3, 1),   # 2
            JOYSTICK_UP: (3, 2),     # 3
            JOYSTICK_RIGHT: (3, 3),  # 4
            JOYSTICK_FIRE: (3, 4),   # 5
            JOYSTICK_FIRE_2: (7, 0), # Space
        },
    )

    def __init__(
        self,
        rom_data: bytes | None = None,
        *,
        tape_data: bytes | None = None,
        snapshot_data: bytes | None = None,
        display_profile: str = "default",
    ):
        bus = Z80Bus()
        cpu = Z80Core(bus)
        super().__init__(bus=bus, cpu=cpu)
        self.display_profile_name = display_profile
        self.display_profile = get_display_profile(display_profile)

        self.rom = ROMBlock(self.ROM_SIZE)
        self.ram = RAMBlock(self.RAM_SIZE)

        if rom_data is not None:
            self.rom.load_bytes(rom_data)

        self.bus.map_block(0x0000, self.rom)
        # Each model maps only the RAM it physically has. Unmapped pages fall
        # back to the bus default behavior (0xFF on reads, ignored writes).
        self.bus.map_block(self.RAM_BASE, self.ram)

        self.border_color = 0
        self.last_out_fe = 0

        self.ula = Spectrum48KULA(self)
        self.cassette = SpectrumCassetteTape.from_bytes(tape_data) if tape_data is not None else None
        self._tape_tstates = 0
        self.frame_width = self.ula.frame_width
        self.frame_height = self.ula.frame_height
        self.framebuffer_rgb24 = self.ula.framebuffer_rgb24
        self.audio_samples = self.ula.get_frame_samples()
        self.audio_ring = self.audio_ring.__class__(self.ula.beeper.sample_rate // 2)

        self.keyboard_rows = [0x1F] * 8

        self.bus.set_port_handler(
            0xFE,
            PythonPortHandler(self._port_read_fe, self._port_write_fe),
        )
        self._frame_runner = SteppedFrameRunner(self.TSTATES_PER_FRAME)
        self._pending_snapshot_data = snapshot_data

    @property
    def framebuffer_rgb24(self):
        if hasattr(self, "ula"):
            return self.ula.framebuffer_rgb24
        return getattr(self, "_framebuffer_rgb24", None)

    @framebuffer_rgb24.setter
    def framebuffer_rgb24(self, value):
        if hasattr(self, "ula"):
            self.ula.framebuffer_rgb24 = value
            return
        self._framebuffer_rgb24 = value

    @property
    def ram_top(self) -> int:
        return self.RAM_BASE + self.RAM_SIZE

    def _port_read_fe(self, port: int) -> int:
        result = 0xFF
        high = (port >> 8) & 0xFF

        for row in range(8):
            if (high & (1 << row)) == 0:
                result &= self.keyboard_rows[row]

        if self.cassette is not None:
            # EAR input is observed on bit 6. Toggling this bit is enough for
            # the ROM loader to see tape edges.
            if self.cassette.level:
                result &= ~0x40
            else:
                result |= 0x40

        return result & 0xFF

    def _port_write_fe(self, port: int, value: int) -> None:
        value &= 0xFF
        self.last_out_fe = value
        self.border_color = value & 0x07
        self.ula.beeper.set_level_from_port_value(value, self.frame_tstates)

    def reset(self):
        super().reset()
        self.border_color = 0
        self.last_out_fe = 0
        self.keyboard_rows = [0x1F] * 8

        self.ula.reset()
        if self.cassette is not None:
            self.cassette.reset()
        self._tape_tstates = 0
        self.framebuffer_rgb24 = self.ula.framebuffer_rgb24
        self.audio_samples = self.ula.get_frame_samples()
        if self._pending_snapshot_data is not None:
            snapshot = self._pending_snapshot_data
            self._pending_snapshot_data = None
            apply_z80_snapshot(self, snapshot)

    def _begin_frame(self) -> None:
        self.frame_tstates = 0
        self._tape_tstates = 0
        self.ula.begin_frame()
        self.ula.beeper.begin_frame()

    def _finish_frame(self) -> None:
        self.ula.end_frame()
        self.framebuffer_rgb24 = self.ula.framebuffer_rgb24
        self.audio_samples = self.ula.get_frame_samples()
        self.audio_ring.write(self.audio_samples)
        self.frame_counter += 1

    def run_frame(self) -> int:
        self._frame_runner.run(
            self,
            self.cpu.step,
            self._run_devices_until,
            self._begin_frame,
            self._finish_frame,
        )
        return self.tstates

    def _run_devices_until(self, tstates: int):
        self.ula.run_until(tstates)
        if self.cassette is not None:
            self.cassette.run_cycles(max(0, tstates - self._tape_tstates))
            self._tape_tstates = tstates

    def toggle_tape_play_pause(self) -> bool:
        if self.cassette is None:
            return False
        return self.cassette.toggle_play_pause()

    def load_rom(self, data: bytes):
        self.rom.load_bytes(data)

    def _is_ram_address(self, addr: int) -> bool:
        return self.RAM_BASE <= addr < self.ram_top

    def poke(self, addr: int, value: int):
        if self._is_ram_address(addr):
            self.ram.load(addr - self.RAM_BASE, bytes([value & 0xFF]))
            return
        raise ValueError(
            f"solo se puede escribir en RAM 0x{self.RAM_BASE:04X}-0x{self.ram_top - 1:04X}"
        )

    def peek(self, addr: int) -> int:
        if 0x0000 <= addr < self.ROM_SIZE:
            return self.rom.peek(addr)
        if self._is_ram_address(addr):
            return self.ram.peek(addr - self.RAM_BASE)
        if 0 <= addr <= 0xFFFF:
            # Smaller models expose holes above installed RAM. Returning 0xFF
            # keeps the high-level helpers aligned with the underlying bus.
            return 0xFF
        raise ValueError("dirección fuera de rango")

    def load_ram(self, addr: int, data: bytes):
        if not self._is_ram_address(addr) or addr + len(data) > self.ram_top:
            raise ValueError(
                f"el rango debe caer dentro de la RAM del Spectrum "
                f"0x{self.RAM_BASE:04X}-0x{self.ram_top - 1:04X}"
            )
        self.ram.load(addr - self.RAM_BASE, data)

    def clear_input_state(self):
        self.keyboard_rows = [0x1F] * 8

    def _press_key(self, row: int, bit: int):
        self.keyboard_rows[row] &= ~(1 << bit)
        self.keyboard_rows[row] &= 0x1F

    def _release_key(self, row: int, bit: int):
        self.keyboard_rows[row] |= (1 << bit)
        self.keyboard_rows[row] &= 0x1F

    def handle_input_event(self, event):
        if not isinstance(event, InputEvent):
            raise TypeError(f"evento de input inválido: {type(event)!r}")

        if event.kind == "key_matrix":
            if event.active:
                self._press_key(event.control_a, event.control_b)
            else:
                self._release_key(event.control_a, event.control_b)
            return

        if event.kind == "joystick":
            joystick_index = int(event.control_a)
            if not (0 <= joystick_index < len(self.JOYSTICK_KEY_BINDINGS)):
                raise ValueError(f"joystick fuera de rango: {joystick_index}")
            binding = self.JOYSTICK_KEY_BINDINGS[joystick_index].get(int(event.control_b))
            if binding is None:
                return
            if event.active:
                self._press_key(*binding)
            else:
                self._release_key(*binding)
            return

        raise ValueError(f"tipo de input no soportado: {event.kind}")

    def render_frame(self):
        self.framebuffer_rgb24 = self.ula.render_frame()
        return self.framebuffer_rgb24

    def get_audio_samples(self):
        return self.audio_samples

    def snapshot(self) -> dict:
        snap = self.cpu.snapshot()
        snap["border_color"] = self.border_color
        snap["last_out_fe"] = self.last_out_fe
        snap["tstates"] = self.tstates
        snap["frame_counter"] = self.frame_counter
        snap["frame_tstates"] = self.frame_tstates
        snap["ram_base"] = self.RAM_BASE
        snap["ram_size"] = self.RAM_SIZE
        return snap

    def read_state(self) -> dict:
        state = super().read_state()
        state |= {
            "border_color": self.border_color,
            "last_out_fe": self.last_out_fe,
            "keyboard_rows": list(self.keyboard_rows),
            "tape_tstates": self._tape_tstates,
            "ram": self.ram.read_state(),
            "ula": self.ula.read_state(),
            "cassette": None if self.cassette is None else self.cassette.read_state(),
        }
        return state

    def write_state(self, state: dict) -> None:
        super().write_state(state)
        if "border_color" in state:
            self.border_color = int(state["border_color"]) & 0x07
        if "last_out_fe" in state:
            self.last_out_fe = int(state["last_out_fe"]) & 0xFF
        if "keyboard_rows" in state:
            self.keyboard_rows = restore_fixed_length_list(
                state["keyboard_rows"],
                length=8,
                mask=0x1F,
                fill=0x1F,
            )
        if "tape_tstates" in state:
            self._tape_tstates = int(state["tape_tstates"])
        if "ram" in state:
            self.ram.write_state(state["ram"])
        if "ula" in state:
            self.ula.write_state(state["ula"])
        if self.cassette is not None and state.get("cassette") is not None:
            self.cassette.write_state(state["cassette"])
        self.framebuffer_rgb24 = self.ula.framebuffer_rgb24
        self.audio_samples = self.ula.get_frame_samples()

    def debug_devices(self) -> list[dict]:
        devices = build_debug_devices(
            self,
            super().debug_devices(),
            [
                ("rom", self.rom, "memory", "ROM", None),
                ("ram", self.ram, "memory", "RAM", None),
                ("ula", self.ula, "chip", "ULA", None),
            ],
        )
        if self.cassette is not None:
            devices.append(self._debug_device("cassette", self.cassette, "device", label="Cassette"))
        return devices


class Spectrum16K(SpectrumBase):
    """ZX Spectrum 16K with RAM only in 0x4000-0x7FFF."""

    RAM_SIZE = 0x4000


class Spectrum48K(SpectrumBase):
    """ZX Spectrum 48K with the full 0x4000-0xFFFF RAM space mapped."""

    input_keymap_name = "spectrum48k"
    RAM_SIZE = 0xC000


class Spectrum128KMemoryMap(MemoryDevice):
    """Expose paged Spectrum 128K memory through the generic Z80 bus."""

    def __init__(self, machine: "Spectrum128K"):
        self.machine = machine

    def read(self, addr):
        return self.machine.peek(addr)

    def write(self, addr, value):
        if self.machine._is_ram_address(addr):
            self.machine.poke(addr, value)


class Spectrum128K(SpectrumBase):
    """ZX Spectrum 128K scaffold with 0x7FFD paging and AY sound."""

    input_keymap_name = "spectrum128k"
    RAM_BANK_SIZE = 0x4000
    RAM_BANK_COUNT = 8
    AY_CLOCK_HZ = 1_773_400

    def __init__(
        self,
        rom_data: bytes | None = None,
        *,
        tape_data: bytes | None = None,
        snapshot_data: bytes | None = None,
        display_profile: str = "default",
    ):
        bus = Z80Bus()
        cpu = Z80Core(bus)
        BaseMachine.__init__(self, bus=bus, cpu=cpu)
        self.machine_id = "spectrum128k"
        self.display_profile_name = display_profile
        self.display_profile = get_display_profile(display_profile)

        self.rom_banks = [ROMBlock(self.ROM_SIZE), ROMBlock(self.ROM_SIZE)]
        self.ram_banks = [RAMBlock(self.RAM_BANK_SIZE) for _ in range(self.RAM_BANK_COUNT)]
        self.ram = self.ram_banks[5]
        if rom_data is not None:
            self.load_rom(rom_data)

        self.active_rom_bank = 0
        self.paged_ram_bank = 0
        self.screen_bank = 5
        self.paging_locked = False
        self.border_color = 0
        self.last_out_fe = 0
        self.last_out_7ffd = 0

        self.memory_map = Spectrum128KMemoryMap(self)
        self.bus.map_device(0x0000, 0x10000, self.memory_map)

        self.ula = Spectrum48KULA(self)
        self.cassette = SpectrumCassetteTape.from_bytes(tape_data) if tape_data is not None else None
        self._tape_tstates = 0
        self.frame_width = self.ula.frame_width
        self.frame_height = self.ula.frame_height
        self.framebuffer_rgb24 = self.ula.framebuffer_rgb24
        self.audio_samples = self.ula.get_frame_samples()
        self.audio_ring = self.audio_ring.__class__(self.ula.beeper.sample_rate // 2)

        self.psg = AY38912(clock_hz=self.AY_CLOCK_HZ, sample_rate=44100)
        self.psg.select_register(0)

        self.keyboard_rows = [0x1F] * 8
        for port_low in range(256):
            self.bus.set_port_handler(port_low, PythonPortHandler(self._port_read, self._port_write))
        self._frame_runner = SteppedFrameRunner(self.TSTATES_PER_FRAME)
        self._pending_snapshot_data = snapshot_data

    def _mix_audio_frame(self):
        beeper = self.ula.get_frame_samples()
        ay = self.psg.render_samples(len(beeper))
        mixed = array("h", [0] * len(beeper))
        for i in range(len(beeper)):
            sample = int(beeper[i]) + int(ay[i])
            if sample > 32767:
                sample = 32767
            elif sample < -32768:
                sample = -32768
            mixed[i] = sample
        return mixed

    def _port_read(self, port: int) -> int:
        if (port & 0x0001) == 0:
            return self._port_read_fe(port)
        if (port & 0xC002) == 0xC000:
            return self.psg.read_selected()
        return 0xFF

    def _port_write(self, port: int, value: int) -> None:
        value &= 0xFF
        if (port & 0x0001) == 0:
            self._port_write_fe(port, value)
        if (port & 0x8002) == 0:
            self._write_7ffd(value)
        if (port & 0xC002) == 0xC000:
            self.psg.select_register(value & 0x0F)
        elif (port & 0xC002) == 0x8000:
            self.psg.write_selected(value)

    def _write_7ffd(self, value: int) -> None:
        if self.paging_locked:
            return
        self.last_out_7ffd = value & 0xFF
        self.paged_ram_bank = value & 0x07
        self.screen_bank = 7 if (value & 0x08) else 5
        self.active_rom_bank = 1 if (value & 0x10) else 0
        if value & 0x20:
            self.paging_locked = True
        self.ula.set_display_ram(self.ram_banks[self.screen_bank])

    def reset(self):
        BaseMachine.reset(self)
        self.active_rom_bank = 0
        self.paged_ram_bank = 0
        self.screen_bank = 5
        self.paging_locked = False
        self.border_color = 0
        self.last_out_fe = 0
        self.last_out_7ffd = 0
        self.keyboard_rows = [0x1F] * 8
        self.ula.reset()
        self.ula.set_display_ram(self.ram_banks[self.screen_bank])
        self.psg.reset()
        if self.cassette is not None:
            self.cassette.reset()
        self._tape_tstates = 0
        self.framebuffer_rgb24 = self.ula.framebuffer_rgb24
        self.audio_samples = self._mix_audio_frame()
        if self._pending_snapshot_data is not None:
            snapshot = self._pending_snapshot_data
            self._pending_snapshot_data = None
            apply_z80_snapshot(self, snapshot)

    def _begin_frame(self) -> None:
        self.frame_tstates = 0
        self._tape_tstates = 0
        self.ula.begin_frame()
        self.ula.beeper.begin_frame()

    def _finish_frame(self) -> None:
        self.ula.end_frame()
        self.framebuffer_rgb24 = self.ula.framebuffer_rgb24
        self.audio_samples = self._mix_audio_frame()
        self.audio_ring.write(self.audio_samples)
        self.frame_counter += 1

    def _run_devices_until(self, tstates: int):
        self.ula.run_until(tstates)
        if self.cassette is not None:
            self.cassette.run_cycles(max(0, tstates - self._tape_tstates))
            self._tape_tstates = tstates

    def load_rom(self, data: bytes):
        if len(data) == self.ROM_SIZE * 2:
            self.rom_banks[0].load_bytes(data[:self.ROM_SIZE])
            self.rom_banks[1].load_bytes(data[self.ROM_SIZE:])
            return
        self.rom_banks[0].load_bytes(data)

    def _is_ram_address(self, addr: int) -> bool:
        return 0x4000 <= addr <= 0xFFFF

    def _ram_bank_for_addr(self, addr: int) -> RAMBlock:
        if 0x4000 <= addr < 0x8000:
            return self.ram_banks[5]
        if 0x8000 <= addr < 0xC000:
            return self.ram_banks[2]
        return self.ram_banks[self.paged_ram_bank]

    @property
    def ram_top(self) -> int:
        return 0x10000

    def poke(self, addr: int, value: int):
        if not self._is_ram_address(addr):
            raise ValueError("solo se puede escribir en RAM 0x4000-0xFFFF")
        self._ram_bank_for_addr(addr).load(addr & 0x3FFF, bytes([value & 0xFF]))

    def peek(self, addr: int) -> int:
        if 0x0000 <= addr < self.ROM_SIZE:
            return self.rom_banks[self.active_rom_bank].peek(addr)
        if self._is_ram_address(addr):
            return self._ram_bank_for_addr(addr).peek(addr & 0x3FFF)
        if 0 <= addr <= 0xFFFF:
            return 0xFF
        raise ValueError("dirección fuera de rango")

    def load_ram_bank(self, bank: int, offset: int, data: bytes):
        self.ram_banks[bank & 0x07].load(offset, data)

    def load_ram(self, addr: int, data: bytes):
        if not self._is_ram_address(addr) or addr + len(data) > self.ram_top:
            raise ValueError("el rango debe caer dentro de la RAM del Spectrum 128K/+2 0x4000-0xFFFF")

        remaining = memoryview(data)
        cursor = addr
        while remaining:
            if 0x4000 <= cursor < 0x8000:
                bank = self.ram_banks[5]
                offset = cursor - 0x4000
                chunk_len = min(len(remaining), 0x8000 - cursor)
            elif 0x8000 <= cursor < 0xC000:
                bank = self.ram_banks[2]
                offset = cursor - 0x8000
                chunk_len = min(len(remaining), 0xC000 - cursor)
            else:
                bank = self.ram_banks[self.paged_ram_bank]
                offset = cursor - 0xC000
                chunk_len = min(len(remaining), 0x10000 - cursor)
            bank.load(offset, remaining[:chunk_len].tobytes())
            remaining = remaining[chunk_len:]
            cursor += chunk_len

    def snapshot(self) -> dict:
        snap = self.cpu.snapshot()
        snap["border_color"] = self.border_color
        snap["last_out_fe"] = self.last_out_fe
        snap["last_out_7ffd"] = self.last_out_7ffd
        snap["active_rom_bank"] = self.active_rom_bank
        snap["paged_ram_bank"] = self.paged_ram_bank
        snap["screen_bank"] = self.screen_bank
        snap["paging_locked"] = self.paging_locked
        snap["tstates"] = self.tstates
        snap["frame_counter"] = self.frame_counter
        snap["frame_tstates"] = self.frame_tstates
        return snap

    def read_state(self) -> dict:
        state = BaseMachine.read_state(self)
        state |= {
            "border_color": self.border_color,
            "last_out_fe": self.last_out_fe,
            "last_out_7ffd": self.last_out_7ffd,
            "active_rom_bank": self.active_rom_bank,
            "paged_ram_bank": self.paged_ram_bank,
            "screen_bank": self.screen_bank,
            "paging_locked": self.paging_locked,
            "keyboard_rows": list(self.keyboard_rows),
            "tape_tstates": self._tape_tstates,
            "ram_banks": [bank.read_state() for bank in self.ram_banks],
            "ula": self.ula.read_state(),
            "psg": self.psg.read_state(),
            "cassette": None if self.cassette is None else self.cassette.read_state(),
        }
        return state

    def write_state(self, state: dict) -> None:
        BaseMachine.write_state(self, state)
        if "border_color" in state:
            self.border_color = int(state["border_color"]) & 0x07
        if "last_out_fe" in state:
            self.last_out_fe = int(state["last_out_fe"]) & 0xFF
        if "last_out_7ffd" in state:
            self.last_out_7ffd = int(state["last_out_7ffd"]) & 0xFF
        if "active_rom_bank" in state:
            self.active_rom_bank = int(state["active_rom_bank"]) & 0x01
        if "paged_ram_bank" in state:
            self.paged_ram_bank = int(state["paged_ram_bank"]) & 0x07
        if "screen_bank" in state:
            self.screen_bank = int(state["screen_bank"]) & 0x07
        if "paging_locked" in state:
            self.paging_locked = bool(state["paging_locked"])
        if "keyboard_rows" in state:
            self.keyboard_rows = restore_fixed_length_list(
                state["keyboard_rows"],
                length=8,
                mask=0x1F,
                fill=0x1F,
            )
        if "tape_tstates" in state:
            self._tape_tstates = int(state["tape_tstates"])
        if "ram_banks" in state:
            for bank, bank_state in zip(self.ram_banks, state["ram_banks"], strict=False):
                bank.write_state(bank_state)
        if "ula" in state:
            self.ula.write_state(state["ula"])
        if "psg" in state:
            self.psg.write_state(state["psg"])
        if self.cassette is not None and state.get("cassette") is not None:
            self.cassette.write_state(state["cassette"])
        self.ram = self.ram_banks[5]
        self.ula.set_display_ram(self.ram_banks[self.screen_bank])
        self.framebuffer_rgb24 = self.ula.framebuffer_rgb24
        self.audio_samples = self._mix_audio_frame()

    def debug_devices(self) -> list[dict]:
        devices = build_debug_devices(
            self,
            super().debug_devices(),
            [
                ("rom0", self.rom_banks[0], "memory", "ROM 0", None),
                ("rom1", self.rom_banks[1], "memory", "ROM 1", None),
                ("ram_bank_5", self.ram_banks[5], "memory", "RAM Bank 5", None),
                ("ram_bank_2", self.ram_banks[2], "memory", "RAM Bank 2", None),
                ("ram_bank_paged", self.ram_banks[self.paged_ram_bank], "memory", "Paged RAM", None),
                ("ula", self.ula, "chip", "ULA", None),
                ("ay", self.psg, "chip", "AY-3-8912", None),
            ],
        )
        if self.cassette is not None:
            devices.append(self._debug_device("cassette", self.cassette, "device", label="Cassette"))
        return devices


class SpectrumPlus2(Spectrum128K):
    """ZX Spectrum +2 scaffold reusing the 128K hardware profile."""

    def __init__(
        self,
        rom_data: bytes | None = None,
        *,
        tape_data: bytes | None = None,
        snapshot_data: bytes | None = None,
        display_profile: str = "default",
    ):
        super().__init__(
            rom_data,
            tape_data=tape_data,
            snapshot_data=snapshot_data,
            display_profile=display_profile,
        )
        self.machine_id = "spectrumplus2"
