from __future__ import annotations

from array import array
from hashlib import sha256

from cpu.z80 import MemoryDevice, PythonPortHandler, ROMBlock, Z80Bus, Z80Core
from chipsets import SMSVDP, SN76489
from frontend.input_events import (
    InputEvent,
    JOYSTICK_DOWN,
    JOYSTICK_FIRE,
    JOYSTICK_FIRE_2,
    JOYSTICK_LEFT,
    JOYSTICK_RIGHT,
    JOYSTICK_START,
    JOYSTICK_UP,
)
from machines.base import BaseMachine
from machines.frame_runner import SteppedFrameRunner


class MasterSystemMemoryMap(MemoryDevice):
    """Expose Master System II RAM/mapping registers through the Z80 bus."""

    def __init__(self, machine: "MasterSystem2"):
        self.machine = machine

    def read(self, addr):
        return self.machine.peek(addr)

    def write(self, addr, value):
        self.machine.poke(addr, value)


class MasterSystemRAMDebugDevice:
    def __init__(self, machine: "MasterSystem2"):
        self.machine = machine

    def read_state(self) -> dict:
        return {
            "__meta__": {"type": "MasterSystemRAM", "size": self.machine.RAM_SIZE},
            "data": list(self.machine.ram),
        }

    def write_state(self, state: dict) -> None:
        if "data" not in state:
            return
        values = bytes(int(v) & 0xFF for v in state["data"])
        if len(values) != self.machine.RAM_SIZE:
            raise ValueError(f"RAM de Master System II debe medir {self.machine.RAM_SIZE} bytes")
        self.machine.ram[:] = values


class MasterSystemMapperDebugDevice:
    def __init__(self, machine: "MasterSystem2"):
        self.machine = machine

    def read_state(self) -> dict:
        return {
            "__meta__": {"type": "MasterSystemMapper"},
            "active_rom_source": self.machine.active_rom_source,
            "mapper_control": self.machine.mapper_control,
            "memory_control": self.machine.memory_control,
            "frame_page_0": self.machine.frame_page_0,
            "frame_page_1": self.machine.frame_page_1,
            "frame_page_2": self.machine.frame_page_2,
        }

    def write_state(self, state: dict) -> None:
        self.machine.write_state({
            key: state[key]
            for key in (
                "active_rom_source",
                "mapper_control",
                "memory_control",
                "frame_page_0",
                "frame_page_1",
                "frame_page_2",
            )
            if key in state
        })


class MasterSystemCartridgeDebugDevice:
    def __init__(self, machine: "MasterSystem2"):
        self.machine = machine

    def read_state(self) -> dict:
        return {
            "__meta__": {"type": "MasterSystemCartridge", "writable": False},
            "active_rom_source": self.machine.active_rom_source,
            "cart_size": len(self.machine.cart_data),
            "bios_size": len(self.machine.bios_data),
            "built_in_size": len(self.machine.built_in_data),
            "cart_sha256": self.machine._rom_sha256(self.machine.cart_data),
            "bios_sha256": self.machine._rom_sha256(self.machine.bios_data),
            "built_in_sha256": self.machine._rom_sha256(self.machine.built_in_data),
        }


class MasterSystem2(BaseMachine):
    """Early Sega Master System II scaffold.

    This is intentionally an early machine scaffold:
    - Z80 CPU
    - cartridge ROM banking
    - system RAM
    - minimal VDP with tiled background rendering
    - basic frame timing
    """

    FRAMES_PER_SECOND = 60
    TSTATES_PER_FRAME = 59_736
    CPU_CLOCK_HZ = 3_579_545
    AUDIO_FRAMES_PER_SECOND = CPU_CLOCK_HZ / TSTATES_PER_FRAME
    TARGET_FPS = AUDIO_FRAMES_PER_SECOND
    PSG_OVERSAMPLE = 8
    AUDIO_CHANNELS = 1
    input_keymap_name = "mastersystem2"
    input_gamepad_map_name = "mastersystem2"
    input_joystick_count = 1

    SCREEN_WIDTH = 256
    SCREEN_HEIGHT = 192
    VDP_FRAME_WIDTH = 256
    VDP_FRAME_HEIGHT = 192
    is_game_gear = False

    PAGE_SIZE = 0x4000
    RAM_SIZE = 0x2000

    def __init__(
        self,
        rom_data: bytes | None = None,
        *,
        bios_data: bytes | None = None,
        built_in_data: bytes | None = None,
        display_profile: str = "default",
        audio_sample_rate: int = 44100,
    ):
        bus = Z80Bus()
        cpu = Z80Core(bus)
        super().__init__(bus=bus, cpu=cpu, audio_sample_rate=audio_sample_rate)

        self.machine_id = "mastersystem2"
        self.display_name = "Sega Master System II (early scaffold)"
        self.display_profile_name = display_profile

        if rom_data is None and bios_data is None:
            raise ValueError("Master System II requiere al menos una ROM de cartucho o BIOS")

        self.cart_data = bytes(rom_data or b"")
        self.bios_data = bytes(bios_data or b"")
        self.built_in_data = bytes(built_in_data or b"")

        if self.bios_data and not self.built_in_data and len(self.bios_data) > 0x8000:
            self.built_in_data = self.bios_data[0x8000:]
            self.bios_data = self.bios_data[:0x8000]

        self.cart_banks = self._split_rom_banks(self.cart_data)
        self.bios_banks = self._split_rom_banks(self.bios_data)
        self.built_in_banks = self._split_rom_banks(self.built_in_data)
        self._open_bus_bank = bytes([0xFF]) * self.PAGE_SIZE
        self.active_rom_source = "bios" if bios_data is not None else "cart"
        self.ram = bytearray(self.RAM_SIZE)

        self.frame_width = self.SCREEN_WIDTH
        self.frame_height = self.SCREEN_HEIGHT
        self.audio_output_sample_rate = int(audio_sample_rate)
        self.audio_internal_sample_rate = int(audio_sample_rate) * self.PSG_OVERSAMPLE
        self.audio_samples = array("h")
        self.samples_per_frame = int(round(audio_sample_rate / self.AUDIO_FRAMES_PER_SECOND))
        self._audio_samples_per_frame_exact = float(audio_sample_rate) / self.AUDIO_FRAMES_PER_SECOND
        self._audio_sample_fraction = 0.0
        self._frame_audio = array("h")
        self._audio_rendered_samples = 0
        self._current_frame_sample_target = self.samples_per_frame
        self._current_frame_internal_sample_target = self.samples_per_frame * self.PSG_OVERSAMPLE
        self._pad1_state = 0xFF
        self.mapper_control = 0x00
        self.memory_control = 0x00
        self.io_control = 0x0F
        self.port_de_value = 0x00
        self.port_df_value = 0x00
        self._visible_bank_0 = self.cart_banks[0]
        self._visible_bank_1 = self.cart_banks[0]
        self._visible_bank_2 = self.cart_banks[0]
        self._rom_window_0 = ROMBlock(self.PAGE_SIZE)
        self._rom_window_1 = ROMBlock(self.PAGE_SIZE)
        self._rom_window_2 = ROMBlock(self.PAGE_SIZE)
        if not self.bios_data:
            self.ram[0] = 0xAB

        self.frame_page_0 = 0
        active_banks = self._active_banks()
        self.frame_page_1 = 1 if len(active_banks) > 1 else 0
        self.frame_page_2 = self._default_page_2()
        self._refresh_visible_banks()

        self.vdp = SMSVDP(self)
        self.psg = SN76489(sample_rate=self.audio_internal_sample_rate)
        self._ram_debug_device = MasterSystemRAMDebugDevice(self)
        self._mapper_debug_device = MasterSystemMapperDebugDevice(self)
        self._cartridge_debug_device = MasterSystemCartridgeDebugDevice(self)
        self.framebuffer_rgb24 = self.vdp.framebuffer_rgb24

        self.memory_map = MasterSystemMemoryMap(self)
        self.bus.map_block(0x0000, self._rom_window_0)
        self.bus.map_block(0x4000, self._rom_window_1)
        self.bus.map_block(0x8000, self._rom_window_2)
        self.bus.map_device(0xC000, 0x4000, self.memory_map)
        for port_low in range(256):
            self.bus.set_port_handler(port_low, PythonPortHandler(self._port_read, self._port_write))

        self._frame_runner = SteppedFrameRunner(self.TSTATES_PER_FRAME)

    @staticmethod
    def _split_rom_banks(rom_data: bytes) -> list[bytes]:
        if not rom_data:
            return [bytes([0xFF]) * MasterSystem2.PAGE_SIZE]

        banks: list[bytes] = []
        for offset in range(0, len(rom_data), MasterSystem2.PAGE_SIZE):
            bank = rom_data[offset:offset + MasterSystem2.PAGE_SIZE]
            if len(bank) < MasterSystem2.PAGE_SIZE:
                bank = bank + bytes([0xFF]) * (MasterSystem2.PAGE_SIZE - len(bank))
            banks.append(bank)
        return banks or [bytes([0xFF]) * MasterSystem2.PAGE_SIZE]

    @staticmethod
    def _rom_sha256(data: bytes) -> str | None:
        if not data:
            return None
        return sha256(data).hexdigest()

    def _validate_state_rom(self, state: dict) -> None:
        expected = {
            "cart": (len(self.cart_data), self._rom_sha256(self.cart_data)),
            "bios": (len(self.bios_data), self._rom_sha256(self.bios_data)),
            "built_in": (len(self.built_in_data), self._rom_sha256(self.built_in_data)),
        }
        for prefix, (actual_size, actual_hash) in expected.items():
            size_key = f"{prefix}_size"
            hash_key = f"{prefix}_sha256"
            if size_key in state and int(state[size_key]) != actual_size:
                raise ValueError(
                    f"snapshot SMS2 incompatible: {prefix} size "
                    f"{state[size_key]} != {actual_size}"
                )
            if hash_key in state and state[hash_key] != actual_hash:
                raise ValueError(f"snapshot SMS2 incompatible: {prefix} SHA256 distinto")

    def _normalize_bank(self, bank: int) -> int:
        banks = self._active_banks()
        if not banks:
            return 0
        return int(bank) % len(banks)

    def _read_rom(self, bank: int, offset: int) -> int:
        bank &= 0xFF
        if self.active_rom_source == "bios" and self.bios_data:
            if offset < self.PAGE_SIZE and bank < len(self.bios_banks):
                return self.bios_banks[self._normalize_bios_bank(bank)][offset]
            if self.built_in_banks:
                return self._internal_slot2_bank(bank)[offset]
            if bank < len(self.bios_banks):
                return self.bios_banks[self._normalize_bios_bank(bank)][offset]
            if self.built_in_banks:
                return self.built_in_banks[bank % len(self.built_in_banks)][offset]
        banks = self._active_banks()
        return banks[self._normalize_bank(bank)][offset]

    def _active_banks(self) -> list[bytes]:
        if self.active_rom_source == "bios" and self.bios_data:
            return self.bios_banks
        if self.active_rom_source == "builtin" and self.built_in_banks:
            return self.built_in_banks
        return self.cart_banks

    def _normalize_bios_bank(self, bank: int) -> int:
        if not self.bios_banks:
            return 0
        return int(bank) % len(self.bios_banks)

    def _internal_bank(self, bank: int) -> bytes:
        internal_banks = self.bios_banks + self.built_in_banks
        if not internal_banks:
            return self._open_bus_bank
        return internal_banks[int(bank) % len(internal_banks)]

    def _fixed_low_kb_bank(self, banks: list[bytes], bank: int) -> bytes:
        """Sega mapper keeps 0x0000-0x03FF fixed to ROM bank 0."""
        if not banks:
            return self._open_bus_bank
        selected = banks[int(bank) % len(banks)]
        return banks[0][:0x0400] + selected[0x0400:]

    def _default_page_2(self) -> int:
        if self.active_rom_source == "bios" and self.built_in_banks:
            return 2
        active_banks = self._active_banks()
        return 2 if len(active_banks) > 2 else self.frame_page_1

    def _select_rom_source_from_memory_control(self) -> None:
        control = self.memory_control & 0xFF

        if control in (0x00, 0xE3):
            self.active_rom_source = "bios"
            return
        if control == 0xEB:
            self.active_rom_source = "none"
            return
        if control in (0xAB, 0xCB) and self.cart_data:
            self.active_rom_source = "cart"
            return
        if control == 0xCB:
            self.active_rom_source = "none"
            return
        bios_enabled = self.bios_data and not (control & 0x08)
        cart_enabled = self.cart_data and not (control & 0x40)
        built_in_enabled = self.built_in_banks and not (control & 0x20)

        if bios_enabled:
            self.active_rom_source = "bios"
            return
        if cart_enabled:
            self.active_rom_source = "cart"
            return
        if built_in_enabled:
            self.active_rom_source = "builtin"
            return
        self.active_rom_source = "none"

    def _refresh_visible_banks(self) -> None:
        if self.active_rom_source == "bios" and self.bios_data:
            self._visible_bank_0 = self.bios_banks[0]
            if self.built_in_banks:
                self._visible_bank_1 = self._internal_bank(self.frame_page_1)
                self._visible_bank_2 = self._internal_bank(self.frame_page_2)
            else:
                self._visible_bank_1 = self.bios_banks[1 if len(self.bios_banks) > 1 else 0]
                self._visible_bank_2 = self.bios_banks[self._normalize_bios_bank(self.frame_page_2)]
        elif self.active_rom_source == "builtin" and self.built_in_banks:
            if self.bios_banks:
                self._visible_bank_0 = self.bios_banks[0]
                self._visible_bank_1 = self._internal_bank(self.frame_page_1)
            else:
                self._visible_bank_0 = self.built_in_banks[self.frame_page_0 % len(self.built_in_banks)]
                self._visible_bank_1 = self.built_in_banks[self.frame_page_1 % len(self.built_in_banks)]
            self._visible_bank_2 = self._internal_bank(self.frame_page_2)
        elif self.active_rom_source == "none":
            self._visible_bank_0 = self._open_bus_bank
            self._visible_bank_1 = self._open_bus_bank
            self._visible_bank_2 = self._open_bus_bank
        else:
            active_banks = self._active_banks()
            self._visible_bank_0 = self._fixed_low_kb_bank(active_banks, self.frame_page_0)
            self._visible_bank_1 = active_banks[self.frame_page_1 % len(active_banks)]
            self._visible_bank_2 = active_banks[self.frame_page_2 % len(active_banks)]

        self._rom_window_0.load_bytes(self._visible_bank_0)
        self._rom_window_1.load_bytes(self._visible_bank_1)
        self._rom_window_2.load_bytes(self._visible_bank_2)

    def _write_frame_register(self, addr: int, value: int) -> None:
        if addr == 0xFFFC:
            self.mapper_control = value & 0xFF
        elif addr == 0xFFFD:
            self.frame_page_0 = self._normalize_bank(value)
        elif addr == 0xFFFE:
            if self.active_rom_source in {"bios", "builtin"} and self.built_in_banks:
                self.frame_page_1 = value & 0xFF
            else:
                self.frame_page_1 = self._normalize_bank(value)
        elif addr == 0xFFFF:
            if self.active_rom_source in {"bios", "builtin"} and self.built_in_banks:
                self.frame_page_2 = value & 0xFF
            else:
                self.frame_page_2 = self._normalize_bank(value)
        self._refresh_visible_banks()

    def _port_read(self, port: int) -> int:
        port &= 0xFF
        if port in (0xDC, 0xC0):
            return self._read_port_dc()
        if port in (0xDD, 0xC1):
            return self._read_port_dd()
        if port == 0x3E:
            return self.memory_control
        if port == 0x3F:
            return self.io_control
        if port == 0xDE:
            return self.port_de_value
        if port == 0xDF:
            return self.port_df_value
        if port in (0x7E, 0x40):
            return self.vdp.read_v_counter()
        if port in (0x7F, 0x41):
            return self.vdp.read_h_counter()
        if port == 0xBE:
            return self.vdp.read_data()
        if port == 0xBF:
            return self.vdp.read_control()
        return 0xFF

    def _port_write(self, port: int, value: int) -> None:
        port &= 0xFF
        value &= 0xFF
        if port == 0xBE:
            self.vdp.write_data(value)
        elif port == 0xBF:
            self.vdp.write_control(value)
        elif port in (0x7E, 0x7F, 0x40, 0x41):
            self._flush_audio_until(self.frame_tstates)
            self.psg.write(value)
        elif port == 0x3E:
            self.memory_control = value
            self._select_rom_source_from_memory_control()
            self._refresh_visible_banks()
        elif port == 0x3F:
            self._write_io_control(value)
        elif port == 0xDE:
            self.port_de_value = value
        elif port == 0xDF:
            self.port_df_value = value

    def reset(self):
        super().reset()
        self.ram[:] = b"\x00" * self.RAM_SIZE
        if not self.bios_data:
            self.ram[0] = 0xAB
        self._pad1_state = 0xFF
        self.mapper_control = 0x00
        self.memory_control = 0x00
        self.io_control = 0x0F
        self.port_de_value = 0x00
        self.port_df_value = 0x00
        self.active_rom_source = "bios" if self.bios_data else "cart"
        self.frame_page_0 = 0
        active_banks = self._active_banks()
        self.frame_page_1 = 1 if len(active_banks) > 1 else 0
        self.frame_page_2 = self._default_page_2()
        self._refresh_visible_banks()
        self.audio_samples = array("h")
        self._audio_sample_fraction = 0.0
        self._frame_audio = array("h")
        self._audio_rendered_samples = 0
        self._current_frame_sample_target = self.samples_per_frame
        self._current_frame_internal_sample_target = self.samples_per_frame * self.PSG_OVERSAMPLE
        self.psg.reset()
        self.vdp.reset()
        self.framebuffer_rgb24 = self._visible_framebuffer(self.vdp.framebuffer_rgb24)

    def _is_ram_address(self, addr: int) -> bool:
        return 0xC000 <= addr <= 0xFFFF

    def peek(self, addr: int) -> int:
        addr &= 0xFFFF
        if addr < 0x4000:
            return self._visible_bank_0[addr]
        if addr < 0x8000:
            return self._visible_bank_1[addr - 0x4000]
        if addr < 0xC000:
            return self._visible_bank_2[addr - 0x8000]
        return self.ram[(addr - 0xC000) & 0x1FFF]

    def poke(self, addr: int, value: int):
        addr &= 0xFFFF
        value &= 0xFF
        if self._is_ram_address(addr):
            self.ram[(addr - 0xC000) & 0x1FFF] = value
        if 0xFFFC <= addr <= 0xFFFF:
            self._write_frame_register(addr, value)

    def _begin_frame(self) -> None:
        self.frame_tstates = 0
        target = self._audio_samples_per_frame_exact + self._audio_sample_fraction
        self._current_frame_sample_target = int(target)
        self._audio_sample_fraction = target - self._current_frame_sample_target
        self._current_frame_internal_sample_target = (
            self._current_frame_sample_target * self.PSG_OVERSAMPLE
        )
        self._frame_audio = array("h")
        self._audio_rendered_samples = 0
        self.vdp.begin_frame()

    def _finish_frame(self) -> None:
        self._flush_audio_until(self.TSTATES_PER_FRAME)
        self.vdp.end_frame()
        self.framebuffer_rgb24 = self._visible_framebuffer(self.vdp.framebuffer_rgb24)
        self.audio_samples = self._downsample_audio_frame(
            self._frame_audio,
            self._current_frame_sample_target,
        )
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

    def render_frame(self):
        self.framebuffer_rgb24 = self._visible_framebuffer(self.vdp.render_frame())
        return self.framebuffer_rgb24

    def _visible_framebuffer(self, packed: bytes) -> bytes:
        return packed

    def _run_devices_until(self, tstates: int):
        self.vdp.run_until(tstates)
        self.vdp._service_interrupt()
 
    def _flush_audio_until(self, tstates: int) -> None:
        target_samples = (
            max(0, min(self.TSTATES_PER_FRAME, tstates)) * self._current_frame_internal_sample_target
        ) // self.TSTATES_PER_FRAME
        delta_samples = target_samples - self._audio_rendered_samples
        if delta_samples > 0:
            if self.audio_channels == 2:
                self._frame_audio.extend(self.psg.render_stereo_samples(delta_samples))
            else:
                self._frame_audio.extend(self.psg.render_samples(delta_samples))
            self._audio_rendered_samples = target_samples

    def _downsample_audio_frame(self, samples: array, output_count: int) -> array:
        output_count = int(output_count)
        channels = self.audio_channels
        out = array("h")
        if output_count <= 0:
            return out
        if not samples:
            out.extend([0] * (output_count * channels))
            return out

        step = self.PSG_OVERSAMPLE
        expected = output_count * step * channels
        if len(samples) < expected:
            samples = array("h", samples)
            samples.extend([0] * (expected - len(samples)))

        frame_stride = step * channels
        for offset in range(0, expected, frame_stride):
            for channel in range(channels):
                total = 0
                for sample_offset in range(offset + channel, offset + frame_stride, channels):
                    total += samples[sample_offset]
                out.append(int(total / step))
        return out

    def clear_input_state(self):
        self._pad1_state = 0xFF

    def _io_pin_level(self, direction_bit: int, output_bit: int, input_level: bool = True) -> int:
        if self.io_control & (1 << direction_bit):
            return 1 if input_level else 0
        return 1 if (self.io_control & (1 << output_bit)) else 0

    def _read_port_dc(self) -> int:
        value = self._pad1_state & 0x1F
        value |= self._io_pin_level(0, 4, bool(self._pad1_state & 0x20)) << 5
        value |= 0xC0
        return value & 0xFF

    def _read_port_dd(self) -> int:
        value = 0x37
        value |= self._io_pin_level(2, 6, True) << 3
        value |= self._io_pin_level(1, 5, True) << 6
        value |= self._io_pin_level(3, 7, True) << 7
        return value & 0xFF

    def _write_io_control(self, value: int) -> None:
        previous_a_th_low = not (self.io_control & 0x02) and not (self.io_control & 0x20)
        previous_b_th_low = not (self.io_control & 0x08) and not (self.io_control & 0x80)
        self.io_control = value & 0xFF
        current_a_th_low = not (self.io_control & 0x02) and not (self.io_control & 0x20)
        current_b_th_low = not (self.io_control & 0x08) and not (self.io_control & 0x80)
        if (previous_a_th_low and not current_a_th_low) or (previous_b_th_low and not current_b_th_low):
            self.vdp.latch_h_counter()

    @staticmethod
    def _pad_mask(group: int, bit: int) -> int | None:
        if group == 0:
            return {
                0: 0x01,  # up
                1: 0x02,  # down
                2: 0x04,  # left
                3: 0x08,  # right
            }.get(bit)
        if group == 1:
            return {
                0: 0x10,  # button 1
                1: 0x20,  # button 2
            }.get(bit)
        return None

    def _set_pad_control(self, group: int, bit: int, active: bool) -> None:
        mask = self._pad_mask(group, bit)
        if mask is None:
            return
        if active:
            self._pad1_state &= ~mask
        else:
            self._pad1_state |= mask
        self._pad1_state &= 0xFF

    def handle_input_event(self, event):
        if not isinstance(event, InputEvent):
            raise TypeError(f"evento de input inválido: {type(event)!r}")

        if event.kind == "key_matrix":
            self._set_pad_control(int(event.control_a), int(event.control_b), bool(event.active))
            return

        if event.kind == "joystick":
            if int(event.control_a) != 0:
                return
            mapping = {
                JOYSTICK_UP: (0, 0),
                JOYSTICK_DOWN: (0, 1),
                JOYSTICK_LEFT: (0, 2),
                JOYSTICK_RIGHT: (0, 3),
                JOYSTICK_FIRE: (1, 0),
                JOYSTICK_FIRE_2: (1, 1),
                JOYSTICK_START: (1, 2),
            }
            control = mapping.get(int(event.control_b))
            if control is None:
                return
            self._set_pad_control(control[0], control[1], bool(event.active))
            return

        raise ValueError(f"tipo de input no soportado: {event.kind}")

    def snapshot(self) -> dict:
        snap = self.cpu.snapshot()
        snap["frame_page_0"] = self.frame_page_0
        snap["frame_page_1"] = self.frame_page_1
        snap["frame_page_2"] = self.frame_page_2
        snap["active_rom_source"] = self.active_rom_source
        snap["mapper_control"] = self.mapper_control
        snap["memory_control"] = self.memory_control
        snap["io_control"] = self.io_control
        snap["port_de_value"] = self.port_de_value
        snap["port_df_value"] = self.port_df_value
        snap["pad1_state"] = self._pad1_state
        snap["tstates"] = self.tstates
        snap["frame_counter"] = self.frame_counter
        snap["frame_tstates"] = self.frame_tstates
        return snap

    def debug_devices(self) -> list[dict]:
        return super().debug_devices() + [
            self._debug_device("cartridge", self._cartridge_debug_device, "memory", label="Cartridge/BIOS ROM", writable=False),
            self._debug_device("mapper", self._mapper_debug_device, "memory", label="Sega mapper"),
            self._debug_device("ram", self._ram_debug_device, "memory", label="System RAM"),
            self._debug_device("vdp", self.vdp, "chip", label="VDP"),
            self._debug_device("psg", self.psg, "chip", label="PSG"),
        ]

    def read_state(self) -> dict:
        state = super().read_state()
        state |= {
            "__meta__": {
                "type": type(self).__name__,
                "module": type(self).__module__,
            },
            "frame_page_0": self.frame_page_0,
            "frame_page_1": self.frame_page_1,
            "frame_page_2": self.frame_page_2,
            "active_rom_source": self.active_rom_source,
            "mapper_control": self.mapper_control,
            "memory_control": self.memory_control,
            "io_control": self.io_control,
            "port_de_value": self.port_de_value,
            "port_df_value": self.port_df_value,
            "pad1_state": self._pad1_state,
            "ram": list(self.ram),
            "cart_size": len(self.cart_data),
            "bios_size": len(self.bios_data),
            "built_in_size": len(self.built_in_data),
            "cart_sha256": self._rom_sha256(self.cart_data),
            "bios_sha256": self._rom_sha256(self.bios_data),
            "built_in_sha256": self._rom_sha256(self.built_in_data),
            "vdp": self.vdp.read_state(),
            "psg": self.psg.read_state(),
        }
        return state

    def write_state(self, state: dict) -> None:
        self._validate_state_rom(state)
        super().write_state(state)
        if "active_rom_source" in state:
            source = str(state["active_rom_source"])
            if source not in {"bios", "cart", "builtin", "none"}:
                raise ValueError(f"fuente ROM inválida para Master System II: {source!r}")
            self.active_rom_source = source
        if "frame_page_0" in state:
            self.frame_page_0 = self._normalize_bank(int(state["frame_page_0"]))
        if "frame_page_1" in state:
            page1 = int(state["frame_page_1"]) & 0xFF
            if self.active_rom_source in {"bios", "builtin"} and self.built_in_banks:
                self.frame_page_1 = page1
            else:
                self.frame_page_1 = self._normalize_bank(page1)
        if "frame_page_2" in state:
            page2 = int(state["frame_page_2"]) & 0xFF
            if self.active_rom_source in {"bios", "builtin"} and self.built_in_banks:
                self.frame_page_2 = page2
            else:
                self.frame_page_2 = self._normalize_bank(page2)
        if "mapper_control" in state:
            self.mapper_control = int(state["mapper_control"]) & 0xFF
        if "memory_control" in state:
            self.memory_control = int(state["memory_control"]) & 0xFF
        if "io_control" in state:
            self.io_control = int(state["io_control"]) & 0xFF
        if "port_de_value" in state:
            self.port_de_value = int(state["port_de_value"]) & 0xFF
        if "port_df_value" in state:
            self.port_df_value = int(state["port_df_value"]) & 0xFF
        if "pad1_state" in state:
            self._pad1_state = int(state["pad1_state"]) & 0xFF
        if "ram" in state:
            values = bytes(int(v) & 0xFF for v in state["ram"])
            if len(values) != self.RAM_SIZE:
                raise ValueError(f"RAM de Master System II debe medir {self.RAM_SIZE} bytes")
            self.ram[:] = values
        if "vdp" in state:
            self.vdp.write_state(state["vdp"])
            self.framebuffer_rgb24 = self._visible_framebuffer(self.vdp.framebuffer_rgb24)
        if "psg" in state:
            self.psg.write_state(state["psg"])
        self._refresh_visible_banks()


class GameGear(MasterSystem2):
    """Sega Game Gear machine built on the SMS-compatible core."""

    SCREEN_WIDTH = 160
    SCREEN_HEIGHT = 144
    VISIBLE_X = 48
    VISIBLE_Y = 24
    is_game_gear = True
    AUDIO_CHANNELS = 2
    input_keymap_name = "gamegear"
    input_gamepad_map_name = "gamegear"

    def __init__(
        self,
        rom_data: bytes | None = None,
        *,
        bios_data: bytes | None = None,
        built_in_data: bytes | None = None,
        display_profile: str = "default",
        audio_sample_rate: int = 44100,
    ):
        super().__init__(
            rom_data,
            bios_data=bios_data,
            built_in_data=built_in_data,
            display_profile=display_profile,
            audio_sample_rate=audio_sample_rate,
        )
        self.machine_id = "gamegear"
        self.display_name = "Sega Game Gear"
        self._start_pressed = False
        self._gg_io_registers = bytearray(6)
        self.frame_width = self.SCREEN_WIDTH
        self.frame_height = self.SCREEN_HEIGHT
        self.framebuffer_rgb24 = self._visible_framebuffer(self.vdp.framebuffer_rgb24)

    def _visible_framebuffer(self, packed: bytes) -> bytes:
        width = self.VDP_FRAME_WIDTH
        x0 = self.VISIBLE_X
        y0 = self.VISIBLE_Y
        row_bytes = width * 3
        visible_row_bytes = self.SCREEN_WIDTH * 3
        out = bytearray(self.SCREEN_WIDTH * self.SCREEN_HEIGHT * 3)
        for row in range(self.SCREEN_HEIGHT):
            src = ((y0 + row) * row_bytes) + (x0 * 3)
            dst = row * visible_row_bytes
            out[dst:dst + visible_row_bytes] = packed[src:src + visible_row_bytes]
        return bytes(out)

    def reset(self):
        super().reset()
        self._start_pressed = False
        self._gg_io_registers[:] = b"\x00" * len(self._gg_io_registers)
        self.framebuffer_rgb24 = self._visible_framebuffer(self.vdp.framebuffer_rgb24)

    def _port_read(self, port: int) -> int:
        port &= 0xFF
        if port == 0x00:
            # Game Gear exposes START on bit 7, active low. The lower bits are
            # region/compatibility lines and stay high in this scaffold.
            return 0x7F if self._start_pressed else 0xFF
        if 0x01 <= port <= 0x05:
            return self._gg_io_registers[port]
        if port == 0x06:
            return self.psg.read_stereo_control()
        return super()._port_read(port)

    def _port_write(self, port: int, value: int) -> None:
        port &= 0xFF
        value &= 0xFF
        if 0x00 <= port <= 0x05:
            self._gg_io_registers[port] = value
            return
        if port == 0x06:
            self._flush_audio_until(self.frame_tstates)
            self.psg.write_stereo_control(value)
            return
        super()._port_write(port, value)

    def clear_input_state(self):
        super().clear_input_state()
        self._start_pressed = False

    def _set_pad_control(self, group: int, bit: int, active: bool) -> None:
        if group == 1 and bit == 2:
            self._start_pressed = bool(active)
            return
        super()._set_pad_control(group, bit, active)

    def read_state(self) -> dict:
        state = super().read_state()
        state["start_pressed"] = self._start_pressed
        state["gg_io_registers"] = list(self._gg_io_registers)
        return state

    def write_state(self, state: dict) -> None:
        super().write_state(state)
        if "start_pressed" in state:
            self._start_pressed = bool(state["start_pressed"])
        if "gg_io_registers" in state:
            values = bytes(int(v) & 0xFF for v in state["gg_io_registers"])
            if len(values) != 6:
                raise ValueError("gg_io_registers debe tener 6 entradas")
            self._gg_io_registers[:] = values
        self.framebuffer_rgb24 = self._visible_framebuffer(self.vdp.framebuffer_rgb24)
