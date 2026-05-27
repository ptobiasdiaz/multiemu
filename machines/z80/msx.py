from __future__ import annotations

from array import array

from cpu.z80 import Z80Bus, Z80Core
from chipsets import AY38912, TMS9918A
from devices.msx_cas import MSXCassetteTape
from devices.msx_memory import MSXMemoryMap
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
from machines.common import (
    ByteArrayMemoryDebugDevice,
    ReadOnlyBlobDebugDevice,
    blob_state_fields,
    build_debug_devices,
    pad_rom,
    restore_byte_array_state,
    restore_fixed_length_list,
    validate_state_blobs,
)
from machines.frame_runner import SteppedFrameRunner
from machines.z80.common import install_uniform_port_handlers
from multiemu.romdb import lookup_msx_mapper


class MSXPPI:
    """Minimal MSX 8255/PPI model for slot select and keyboard scanning."""

    DEFAULT_CONTROL = 0x82

    def __init__(self, machine: "MSX1"):
        self.machine = machine
        self.control = self.DEFAULT_CONTROL
        self.port_a_latch = machine.slot_register
        self.port_b_latch = 0xFF
        self.port_c_latch = 0x00

    @property
    def selected_keyboard_row(self) -> int:
        return self.port_c_latch & 0x0F

    def reset(self) -> None:
        self.control = self.DEFAULT_CONTROL
        self.port_a_latch = self.machine.slot_register
        self.port_b_latch = 0xFF
        self.port_c_latch = 0x00

    def write_port_a(self, value: int) -> None:
        self.port_a_latch = value & 0xFF
        self.machine.slot_register = self.port_a_latch

    def read_port_a(self) -> int:
        return self.port_a_latch & 0xFF

    def write_port_b(self, value: int) -> None:
        self.port_b_latch = value & 0xFF

    def read_port_b(self) -> int:
        row = self.selected_keyboard_row
        if 0 <= row < self.machine.KEYBOARD_ROWS:
            return self.machine.keyboard_matrix[row]
        return 0xFF

    def write_port_c(self, value: int) -> None:
        self.port_c_latch = value & 0xFF

    def read_port_c(self) -> int:
        return self.port_c_latch & 0xFF

    def write_control(self, value: int) -> None:
        value &= 0xFF
        if value & 0x80:
            self.control = value
            return

        bit_index = (value >> 1) & 0x07
        if value & 0x01:
            self.port_c_latch |= 1 << bit_index
        else:
            self.port_c_latch &= ~(1 << bit_index)
        self.port_c_latch &= 0xFF

    def read_state(self) -> dict:
        return {
            "__meta__": {"type": "MSXPPI"},
            "control": self.control,
            "port_a_latch": self.port_a_latch,
            "port_b_latch": self.port_b_latch,
            "port_c_latch": self.port_c_latch,
        }

    def write_state(self, state: dict) -> None:
        if "control" in state:
            self.control = int(state["control"]) & 0xFF
        if "port_a_latch" in state:
            self.port_a_latch = int(state["port_a_latch"]) & 0xFF
            self.machine.slot_register = self.port_a_latch
        if "port_b_latch" in state:
            self.port_b_latch = int(state["port_b_latch"]) & 0xFF
        if "port_c_latch" in state:
            self.port_c_latch = int(state["port_c_latch"]) & 0xFF


class MSX1(BaseMachine):
    """Minimal MSX1 scaffold: BIOS+BASIC, RAM, TMS9918A, AY and keyboard."""

    CPU_CLOCK_HZ = 3_579_545
    PSG_CLOCK_HZ = CPU_CLOCK_HZ // 2
    PSG_OVERSAMPLE = 2
    FRAMES_PER_SECOND = 60
    TSTATES_PER_FRAME = 59_736
    AUDIO_FRAMES_PER_SECOND = CPU_CLOCK_HZ / TSTATES_PER_FRAME
    TARGET_FPS = AUDIO_FRAMES_PER_SECOND
    AUDIO_CHANNELS = 1

    SCREEN_WIDTH = 256
    SCREEN_HEIGHT = 192
    PAGE_SIZE = 0x4000
    CART_BANK_SIZE = 0x2000
    BIOS_SIZE = 0x4000
    BASIC_SIZE = 0x4000
    CART_WINDOW_SIZE = 0x8000
    RAM_SIZE = 0x10000
    KEYBOARD_ROWS = 11
    DEFAULT_SLOT_REGISTER = 0xF0
    DEFAULT_SLOT_REGISTER_CART1 = 0xD4
    DEFAULT_SLOT_REGISTER_CART2 = 0xE8
    DEFAULT_SUBSLOT_REGISTER = 0xF0
    CART_MAPPER_LINEAR = "linear"
    CART_MAPPER_UNKNOWN = "unknown"
    CART_MAPPER_ASCII8 = "ascii8"
    CART_MAPPER_ASCII16 = "ascii16"
    CART_MAPPER_CROSS_BLAIM = "cross_blaim"
    CART_MAPPER_GENERIC8 = "generic8"
    CART_MAPPER_GENERIC16 = "generic16"
    CART_MAPPER_HARRY_FOX = "harry_fox"
    CART_MAPPER_HOLY_QURAN = "holy_quran"
    CART_MAPPER_KONAMI = "konami"
    CART_MAPPER_KONAMI_SCC = "konami_scc"
    CART_MAPPER_RTYPE = "rtype"
    CART_MAPPER_ZEMINA8 = "zemina8"
    CART_MAPPER_ZEMINA16 = "zemina16"
    CART_MAPPER_ALIASES = {
        "0": CART_MAPPER_GENERIC8,
        "1": CART_MAPPER_GENERIC16,
        "2": CART_MAPPER_KONAMI_SCC,
        "3": CART_MAPPER_KONAMI,
        "4": CART_MAPPER_ASCII8,
        "5": CART_MAPPER_ASCII16,
        "8kb": CART_MAPPER_GENERIC8,
        "16kb": CART_MAPPER_GENERIC16,
        "alquandecoded": CART_MAPPER_HOLY_QURAN,
        "alquran": CART_MAPPER_HOLY_QURAN,
        "alqurandecoded": CART_MAPPER_HOLY_QURAN,
        "ascii8": CART_MAPPER_ASCII8,
        "ascii16": CART_MAPPER_ASCII16,
        "crossblaim": CART_MAPPER_CROSS_BLAIM,
        "generic8": CART_MAPPER_GENERIC8,
        "generickonami": CART_MAPPER_GENERIC8,
        "generic16": CART_MAPPER_GENERIC16,
        "harryfox": CART_MAPPER_HARRY_FOX,
        "holyquran": CART_MAPPER_HOLY_QURAN,
        "konami": CART_MAPPER_KONAMI,
        "konami4": CART_MAPPER_KONAMI,
        "konami5": CART_MAPPER_KONAMI_SCC,
        "konamiscc": CART_MAPPER_KONAMI_SCC,
        "linear": CART_MAPPER_LINEAR,
        "mirrored": CART_MAPPER_LINEAR,
        "normal": CART_MAPPER_LINEAR,
        "rtype": CART_MAPPER_RTYPE,
        "r-type": CART_MAPPER_RTYPE,
        "scc": CART_MAPPER_KONAMI_SCC,
        "unknown": CART_MAPPER_UNKNOWN,
        "zemina8": CART_MAPPER_ZEMINA8,
        "zemina16": CART_MAPPER_ZEMINA16,
    }
    CART_MAPPER_IDS = frozenset(CART_MAPPER_ALIASES.values())
    BIOS_TAPION = 0x00E1
    BIOS_TAPIN = 0x00E4
    BIOS_TAPIOF = 0x00E7

    input_keymap_name = "msx"
    input_gamepad_map_name = "msx"
    input_joystick_count = 2
    input_tap_hold_frames = 1
    input_quick_tap_max_frames = 1

    def __init__(
        self,
        bios_data: bytes,
        *,
        basic_data: bytes | None = None,
        cart1_data: bytes | None = None,
        cart2_data: bytes | None = None,
        cart1_mapper: str | None = None,
        cart2_mapper: str | None = None,
        tape_data: bytes | None = None,
        display_profile: str = "default",
        audio_sample_rate: int = 44100,
    ):
        bus = Z80Bus()
        cpu = Z80Core(bus)
        super().__init__(bus=bus, cpu=cpu, audio_sample_rate=audio_sample_rate)

        self.machine_id = "msx"
        self.display_name = "MSX1 (experimental)"
        self.display_profile_name = display_profile

        self.bios_blob = bytes(bios_data)
        self.basic_blob = bytes(basic_data or b"")
        self.cart1_blob = bytes(cart1_data or b"")
        self.cart2_blob = bytes(cart2_data or b"")
        self.tape_blob = bytes(tape_data or b"")
        self.tape = MSXCassetteTape.from_bytes(self.tape_blob) if self.tape_blob else None
        self.bios_data = pad_rom(self.bios_blob, self.BIOS_SIZE)
        self.basic_data = pad_rom(self.basic_blob, self.BASIC_SIZE) if self.basic_blob else b""
        self.cart1_data = self.cart1_blob[:self.CART_WINDOW_SIZE]
        self.cart2_data = self.cart2_blob[:self.CART_WINDOW_SIZE]
        self.cart1_banks = self._split_cart_banks(self.cart1_blob)
        self.cart2_banks = self._split_cart_banks(self.cart2_blob)
        self.cart1_mapper_override = self._normalize_cart_mapper_id(cart1_mapper) if cart1_mapper else None
        self.cart2_mapper_override = self._normalize_cart_mapper_id(cart2_mapper) if cart2_mapper else None
        self.cart1_mapper = self._select_cart_mapper(
            self.cart1_blob,
            self.cart1_banks,
            self.cart1_mapper_override,
        )
        self.cart2_mapper = self._select_cart_mapper(
            self.cart2_blob,
            self.cart2_banks,
            self.cart2_mapper_override,
        )
        self.cart1_bank_registers = self._default_cart_bank_registers(self.cart1_mapper)
        self.cart2_bank_registers = self._default_cart_bank_registers(self.cart2_mapper)
        self.ram = bytearray(self.RAM_SIZE)
        self.slot_register = self._default_slot_register()
        self.subslot_register = self.DEFAULT_SUBSLOT_REGISTER
        self.keyboard_matrix = [0xFF] * self.KEYBOARD_ROWS
        self.joystick_ports = [0x3F, 0x3F]
        self.psg_port_b_output = 0x00
        self._cassette_activity_frames = 0

        self.frame_width = self.SCREEN_WIDTH
        self.frame_height = self.SCREEN_HEIGHT
        self.framebuffer_rgb24 = bytes(self.SCREEN_WIDTH * self.SCREEN_HEIGHT * 3)
        self.audio_internal_sample_rate = int(audio_sample_rate) * self.PSG_OVERSAMPLE
        self.samples_per_frame = int(round(audio_sample_rate / self.AUDIO_FRAMES_PER_SECOND))
        self._audio_samples_per_frame_exact = float(audio_sample_rate) / self.AUDIO_FRAMES_PER_SECOND
        self._audio_sample_fraction = 0.0
        self._frame_audio = array("h")
        self._audio_rendered_samples = 0
        self._current_frame_sample_target = self.samples_per_frame
        self._current_frame_internal_sample_target = self.samples_per_frame * self.PSG_OVERSAMPLE

        self.vdp = TMS9918A(self)
        self.psg = AY38912(
            clock_hz=self.PSG_CLOCK_HZ,
            sample_rate=self.audio_internal_sample_rate,
            port_a_read=self._read_psg_port_a,
            port_a_read_through_output=True,
            port_b_write=self._write_psg_port_b,
        )
        self._configure_psg_defaults()
        self.ppi = MSXPPI(self)
        self.memory_map = MSXMemoryMap(self)
        self._bios_debug_device = ReadOnlyBlobDebugDevice(
            self,
            attr_name="bios_blob",
            meta_type="MSXBIOS",
        )
        self._basic_debug_device = ReadOnlyBlobDebugDevice(
            self,
            attr_name="basic_blob",
            meta_type="MSXBASIC",
        )
        self._cart1_debug_device = ReadOnlyBlobDebugDevice(
            self,
            attr_name="cart1_blob",
            meta_type="MSXCart1",
        )
        self._cart2_debug_device = ReadOnlyBlobDebugDevice(
            self,
            attr_name="cart2_blob",
            meta_type="MSXCart2",
        )
        self._tape_debug_device = ReadOnlyBlobDebugDevice(
            self,
            attr_name="tape_blob",
            meta_type="MSXCAS",
        )
        self._ram_debug_device = ByteArrayMemoryDebugDevice(
            self,
            attr_name="ram",
            size=self.RAM_SIZE,
            meta_type="MSXRAM",
        )
        self.framebuffer_rgb24 = self.vdp.framebuffer_rgb24

        self.bus.map_device(0x0000, 0x10000, self.memory_map)
        install_uniform_port_handlers(self.bus, self._port_read, self._port_write)
        self._frame_runner = SteppedFrameRunner(self.TSTATES_PER_FRAME)

    def reset(self):
        super().reset()
        self.slot_register = self._default_slot_register()
        self.subslot_register = self.DEFAULT_SUBSLOT_REGISTER
        self.keyboard_matrix = [0xFF] * self.KEYBOARD_ROWS
        self.joystick_ports = [0x3F, 0x3F]
        self.psg_port_b_output = 0x00
        self._cassette_activity_frames = 0
        self.cart1_mapper = self._select_cart_mapper(
            self.cart1_blob,
            self.cart1_banks,
            self.cart1_mapper_override,
        )
        self.cart2_mapper = self._select_cart_mapper(
            self.cart2_blob,
            self.cart2_banks,
            self.cart2_mapper_override,
        )
        self.cart1_bank_registers = self._default_cart_bank_registers(self.cart1_mapper)
        self.cart2_bank_registers = self._default_cart_bank_registers(self.cart2_mapper)
        self.vdp.reset()
        self.psg.reset()
        self.ppi.reset()
        self._audio_sample_fraction = 0.0
        self._frame_audio = array("h")
        self._audio_rendered_samples = 0
        self._current_frame_sample_target = self.samples_per_frame
        self._current_frame_internal_sample_target = self.samples_per_frame * self.PSG_OVERSAMPLE
        if self.tape is not None:
            self.tape.reset()
        self._configure_psg_defaults()
        self.framebuffer_rgb24 = self.vdp.framebuffer_rgb24
        self.audio_samples = array("h", [0] * self.samples_per_frame)

    def _default_slot_register(self) -> int:
        if self.cart1_blob:
            return self.DEFAULT_SLOT_REGISTER_CART1
        if self.cart2_blob:
            return self.DEFAULT_SLOT_REGISTER_CART2
        return self.DEFAULT_SLOT_REGISTER

    def _configure_psg_defaults(self) -> None:
        # On MSX the PSG port A is used as input and port B as output.
        self.psg.registers[7] = (self.psg.registers[7] | 0x40) & 0x7F
        self.psg.registers[15] = 0x00

    def _split_cart_banks(self, cart_blob: bytes) -> list[bytes]:
        if not cart_blob:
            return []
        padded_size = ((len(cart_blob) + self.CART_BANK_SIZE - 1) // self.CART_BANK_SIZE) * self.CART_BANK_SIZE
        padded = pad_rom(cart_blob, padded_size)
        return [
            padded[offset:offset + self.CART_BANK_SIZE]
            for offset in range(0, len(padded), self.CART_BANK_SIZE)
        ]

    def _normalize_cart_mapper_id(self, mapper: str) -> str:
        key = "".join(char for char in str(mapper).strip().lower() if char not in " _-")
        try:
            return self.CART_MAPPER_ALIASES[key]
        except KeyError as exc:
            supported = ", ".join(sorted(self.CART_MAPPER_IDS))
            raise ValueError(f"mapper MSX no soportado en ROM DB: {mapper!r}. Soportados: {supported}") from exc

    def _default_cart_mapper(self, cart_blob: bytes, cart_banks: list[bytes]) -> str:
        if not cart_blob:
            return self.CART_MAPPER_LINEAR
        db_mapper = lookup_msx_mapper(cart_blob)
        if db_mapper is not None:
            return self._normalize_cart_mapper_id(db_mapper)
        if len(cart_banks) <= 4:
            return self.CART_MAPPER_LINEAR
        return self._guess_cart_mapper(cart_blob) or self.CART_MAPPER_UNKNOWN

    def _guess_cart_mapper(self, cart_blob: bytes) -> str | None:
        scores = {
            self.CART_MAPPER_KONAMI: 0,
            self.CART_MAPPER_KONAMI_SCC: 0,
            self.CART_MAPPER_ASCII8: 0,
            self.CART_MAPPER_ASCII16: 0,
        }
        for offset in range(0, max(0, len(cart_blob) - 2)):
            if cart_blob[offset] != 0x32:
                continue
            address = cart_blob[offset + 1] | (cart_blob[offset + 2] << 8)
            if address in (0x5000, 0x9000, 0xB000):
                scores[self.CART_MAPPER_KONAMI_SCC] += 1
            elif address in (0x4000, 0x8000, 0xA000):
                scores[self.CART_MAPPER_KONAMI] += 1
            elif address in (0x6800, 0x7800):
                scores[self.CART_MAPPER_ASCII8] += 1
            elif address == 0x6000:
                scores[self.CART_MAPPER_KONAMI] += 1
                scores[self.CART_MAPPER_ASCII8] += 1
                scores[self.CART_MAPPER_ASCII16] += 1
            elif address == 0x7000:
                scores[self.CART_MAPPER_KONAMI_SCC] += 1
                scores[self.CART_MAPPER_ASCII8] += 1
                scores[self.CART_MAPPER_ASCII16] += 1
            elif address == 0x77FF:
                scores[self.CART_MAPPER_ASCII16] += 1

        if scores[self.CART_MAPPER_ASCII8] > 0:
            scores[self.CART_MAPPER_ASCII8] -= 1

        best_mapper = None
        best_score = 0
        for mapper in (
            self.CART_MAPPER_KONAMI,
            self.CART_MAPPER_KONAMI_SCC,
            self.CART_MAPPER_ASCII8,
            self.CART_MAPPER_ASCII16,
        ):
            score = scores[mapper]
            if score >= best_score and score > 0:
                best_mapper = mapper
                best_score = score
        return best_mapper

    def _select_cart_mapper(
        self,
        cart_blob: bytes,
        cart_banks: list[bytes],
        mapper_override: str | None,
    ) -> str:
        if mapper_override is not None:
            return mapper_override
        return self._default_cart_mapper(cart_blob, cart_banks)

    def _default_cart_bank_registers(self, mapper: str) -> list[int]:
        if mapper == self.CART_MAPPER_ASCII16:
            return [0, 0, 0, 0]
        if mapper == self.CART_MAPPER_ASCII8:
            return [0, 0, 0, 0]
        if mapper == self.CART_MAPPER_HOLY_QURAN:
            return [0, 0, 0, 0]
        if mapper == self.CART_MAPPER_CROSS_BLAIM:
            return [0, 0, 0, 0]
        if mapper == self.CART_MAPPER_RTYPE:
            return [0x17, 0, 0, 0]
        if mapper == self.CART_MAPPER_GENERIC16 or mapper == self.CART_MAPPER_ZEMINA16:
            return [0, 1, 0, 0]
        if mapper == self.CART_MAPPER_HARRY_FOX:
            return [0, 1, 0, 0]
        return [0, 1, 2, 3]

    def _read_16k_cart_bank(self, cart_banks: list[bytes], bank16: int, offset: int) -> int:
        bank_pairs = max(1, len(cart_banks) // 2)
        bank = ((bank16 & 0xFF) % bank_pairs) * 2
        if offset >= self.CART_BANK_SIZE:
            bank += 1
        return cart_banks[bank % len(cart_banks)][offset & (self.CART_BANK_SIZE - 1)]

    def _begin_frame(self) -> None:
        self.frame_tstates = 0
        self.vdp.begin_frame()
        target = self._audio_samples_per_frame_exact + self._audio_sample_fraction
        self._current_frame_sample_target = int(target)
        self._audio_sample_fraction = target - self._current_frame_sample_target
        self._current_frame_internal_sample_target = (
            self._current_frame_sample_target * self.PSG_OVERSAMPLE
        )
        self._frame_audio = array("h")
        self._audio_rendered_samples = 0

    def _finish_frame(self) -> None:
        self.vdp.end_frame()
        self.framebuffer_rgb24 = self.vdp.framebuffer_rgb24
        self._flush_audio_until(self.TSTATES_PER_FRAME)
        self.audio_samples = self._downsample_audio_frame(
            self._frame_audio,
            self._current_frame_sample_target,
        )
        self.audio_ring.write(self.audio_samples)
        self.frame_counter += 1
        if self._cassette_activity_frames > 0:
            self._cassette_activity_frames -= 1

    def run_frame(self) -> int:
        self._frame_runner.run(
            self,
            self._step_cpu if self.tape is not None else self.cpu.step,
            self._run_devices_until,
            self._begin_frame,
            self._finish_frame,
        )
        return self.tstates

    def _step_cpu(self) -> int:
        if self.tape is not None and self._handle_cassette_bios_call():
            return 11
        return self.cpu.step()

    def _handle_cassette_bios_call(self) -> bool:
        pc = self.cpu.PC
        if pc == self.BIOS_TAPION:
            self._bios_return(carry_set=not (self.tape and self.tape.open_for_read()))
            return True
        if pc == self.BIOS_TAPIN:
            value = self.tape.read_byte() if self.tape is not None else None
            if value is not None:
                self._cassette_activity_frames = 30
            self._bios_return(carry_set=value is None, a=value)
            return True
        if pc == self.BIOS_TAPIOF:
            if self.tape is not None:
                self.tape.close()
            self._bios_return(carry_set=False)
            return True
        return False

    def _bios_return(self, *, carry_set: bool, a: int | None = None) -> None:
        sp = self.cpu.SP & 0xFFFF
        ret = self.peek(sp) | (self.peek((sp + 1) & 0xFFFF) << 8)
        self.cpu.PC = ret
        self.cpu.SP = (sp + 2) & 0xFFFF
        self.cpu.F = (self.cpu.F | 0x01) if carry_set else (self.cpu.F & 0xFE)
        if a is not None:
            self.cpu.A = a & 0xFF

    def _run_devices_until(self, tstates: int):
        self.vdp.run_until(tstates)
        if self.vdp.interrupt_line_asserted and self.cpu.interrupts_enabled():
            self.cpu.interrupt()

    def _flush_audio_until(self, tstates: int) -> None:
        target_samples = (
            max(0, min(self.TSTATES_PER_FRAME, tstates)) * self._current_frame_internal_sample_target
        ) // self.TSTATES_PER_FRAME
        delta_samples = target_samples - self._audio_rendered_samples
        if delta_samples > 0:
            self._frame_audio.extend(self.psg.render_samples(delta_samples))
            self._audio_rendered_samples = target_samples

    def _downsample_audio_frame(self, samples: array, output_count: int) -> array:
        output_count = int(output_count)
        out = array("h")
        if output_count <= 0:
            return out
        if not samples:
            out.extend([0] * output_count)
            return out

        step = self.PSG_OVERSAMPLE
        expected = output_count * step
        if len(samples) < expected:
            samples = array("h", samples)
            samples.extend([0] * (expected - len(samples)))

        for offset in range(0, expected, step):
            total = 0
            for sample in samples[offset:offset + step]:
                total += sample
            out.append(int(total / step))
        return out

    def render_frame(self):
        return self.framebuffer_rgb24

    @property
    def cassette_status(self) -> dict | None:
        if self.tape is None:
            return None
        total = max(1, self.tape.total_bytes)
        read = max(0, min(self.tape.bytes_read, total))
        return {
            "present": True,
            "active": self._cassette_activity_frames > 0,
            "opened": self.tape.opened,
            "bytes_read": read,
            "total_bytes": total,
            "percent": int((read * 100) / total),
        }

    def _page_slot(self, page: int) -> int:
        return (self.slot_register >> (page * 2)) & 0x03

    def _page_subslot(self, page: int) -> int:
        return (self.subslot_register >> (page * 2)) & 0x03

    def _read_cart_window(
        self,
        cart_data: bytes,
        cart_banks: list[bytes],
        bank_registers: list[int],
        mapper: str,
        page: int,
        offset: int,
    ) -> int:
        if mapper == self.CART_MAPPER_LINEAR or len(cart_banks) <= 4 or not cart_banks:
            if page not in (1, 2):
                return 0xFF
            index = ((page - 1) * self.PAGE_SIZE) + offset
            if 0 <= index < len(cart_data):
                return cart_data[index]
            return 0xFF

        if mapper == self.CART_MAPPER_KONAMI:
            if page == 0:
                page = 1
            elif page == 3:
                page = 2
            elif page not in (1, 2):
                return 0xFF
            if page == 1 and offset < self.CART_BANK_SIZE:
                return cart_banks[0][offset]
            if page == 1:
                bank = bank_registers[1] % len(cart_banks)
                return cart_banks[bank][offset - self.CART_BANK_SIZE]
            if page == 2 and offset < self.CART_BANK_SIZE:
                bank = bank_registers[2] % len(cart_banks)
                return cart_banks[bank][offset]
            bank = bank_registers[3] % len(cart_banks)
            return cart_banks[bank][offset - self.CART_BANK_SIZE]

        if mapper == self.CART_MAPPER_KONAMI_SCC:
            if page == 0:
                page = 2
            elif page == 3:
                page = 1
            elif page not in (1, 2):
                return 0xFF
            segment = ((page - 1) * 2) + (1 if offset >= self.CART_BANK_SIZE else 0)
            bank = bank_registers[segment] % len(cart_banks)
            bank_offset = offset & (self.CART_BANK_SIZE - 1)
            return cart_banks[bank][bank_offset]

        if mapper in (
            self.CART_MAPPER_ASCII8,
            self.CART_MAPPER_GENERIC8,
            self.CART_MAPPER_ZEMINA8,
            self.CART_MAPPER_HOLY_QURAN,
        ):
            if page not in (1, 2):
                return 0xFF
            segment = ((page - 1) * 2) + (1 if offset >= self.CART_BANK_SIZE else 0)
            bank = bank_registers[segment] % len(cart_banks)
            bank_offset = offset & (self.CART_BANK_SIZE - 1)
            return cart_banks[bank][bank_offset]

        if mapper == self.CART_MAPPER_CROSS_BLAIM:
            if page not in (1, 2):
                return 0xFF
            if page == 1:
                return self._read_16k_cart_bank(cart_banks, 0, offset)
            return self._read_16k_cart_bank(cart_banks, bank_registers[1], offset)

        if mapper == self.CART_MAPPER_RTYPE:
            if page not in (1, 2):
                return 0xFF
            if page == 1:
                return self._read_16k_cart_bank(cart_banks, 0x17, offset)
            return self._read_16k_cart_bank(cart_banks, bank_registers[1], offset)

        if mapper in (
            self.CART_MAPPER_ASCII16,
            self.CART_MAPPER_GENERIC16,
            self.CART_MAPPER_ZEMINA16,
            self.CART_MAPPER_HARRY_FOX,
        ):
            if page not in (1, 2):
                return 0xFF
            segment = 0 if page == 1 else 1
            return self._read_16k_cart_bank(cart_banks, bank_registers[segment], offset)

        if page not in (1, 2):
            return 0xFF
        segment = ((page - 1) * 2) + (1 if offset >= self.CART_BANK_SIZE else 0)
        bank = bank_registers[segment] % len(cart_banks)
        bank_offset = offset & (self.CART_BANK_SIZE - 1)
        return cart_banks[bank][bank_offset]

    def _write_cart_window(
        self,
        cart_banks: list[bytes],
        bank_registers: list[int],
        mapper_attr: str,
        addr: int,
        value: int,
    ) -> bool:
        if len(cart_banks) <= 4:
            return False
        if not (0x4000 <= addr <= 0xBFFF):
            return False
        mapper = getattr(self, mapper_attr)
        if mapper == self.CART_MAPPER_UNKNOWN:
            if 0x9000 <= addr <= 0x97FF:
                mapper = self.CART_MAPPER_KONAMI_SCC
                setattr(self, mapper_attr, mapper)
                bank_registers[:] = self._default_cart_bank_registers(mapper)
            elif 0x6800 <= addr <= 0x6FFF or 0x7800 <= addr <= 0x7FFF:
                mapper = self.CART_MAPPER_ASCII8
                setattr(self, mapper_attr, mapper)
                bank_registers[:] = self._default_cart_bank_registers(mapper)
            elif 0x6000 <= addr <= 0x67FF or 0x7000 <= addr <= 0x77FF:
                mapper = self.CART_MAPPER_ASCII16
                setattr(self, mapper_attr, mapper)
                bank_registers[:] = self._default_cart_bank_registers(mapper)
            elif 0x8000 <= addr <= 0x9FFF:
                mapper = self.CART_MAPPER_KONAMI
                setattr(self, mapper_attr, mapper)
                bank_registers[:] = self._default_cart_bank_registers(mapper)
            else:
                return False
        if mapper == self.CART_MAPPER_ASCII8:
            if 0x6000 <= addr <= 0x67FF:
                bank_registers[0] = value & 0xFF
                return True
            if 0x6800 <= addr <= 0x6FFF:
                bank_registers[1] = value & 0xFF
                return True
            if 0x7000 <= addr <= 0x77FF:
                bank_registers[2] = value & 0xFF
                return True
            if 0x7800 <= addr <= 0x7FFF:
                bank_registers[3] = value & 0xFF
                return True
            return False
        if mapper in (self.CART_MAPPER_GENERIC8, self.CART_MAPPER_ZEMINA8):
            if 0x4000 <= addr <= 0x5FFF:
                bank_registers[0] = value & 0xFF
                return True
            if 0x6000 <= addr <= 0x7FFF:
                bank_registers[1] = value & 0xFF
                return True
            if 0x8000 <= addr <= 0x9FFF:
                bank_registers[2] = value & 0xFF
                return True
            if 0xA000 <= addr <= 0xBFFF:
                bank_registers[3] = value & 0xFF
                return True
            return False
        if mapper == self.CART_MAPPER_HOLY_QURAN:
            if 0x5000 <= addr <= 0x53FF:
                bank_registers[0] = value & 0xFF
                return True
            if 0x5400 <= addr <= 0x57FF:
                bank_registers[1] = value & 0xFF
                return True
            if 0x5800 <= addr <= 0x5BFF:
                bank_registers[2] = value & 0xFF
                return True
            if 0x5C00 <= addr <= 0x5FFF:
                bank_registers[3] = value & 0xFF
                return True
            return False
        if mapper == self.CART_MAPPER_ASCII16:
            if 0x6000 <= addr <= 0x6FFF:
                bank_registers[0] = value & 0xFF
                return True
            if 0x7000 <= addr <= 0x7FFF:
                bank_registers[1] = value & 0xFF
                return True
            return False
        if mapper == self.CART_MAPPER_HARRY_FOX:
            if 0x6000 <= addr <= 0x6FFF:
                bank_registers[0] = 2 * (value & 0x01)
                return True
            if 0x7000 <= addr <= 0x7FFF:
                bank_registers[1] = (2 * (value & 0x01)) + 1
                return True
            return False
        if mapper in (self.CART_MAPPER_GENERIC16, self.CART_MAPPER_ZEMINA16):
            if 0x4000 <= addr <= 0x7FFF:
                bank_registers[0] = value & 0xFF
                return True
            if 0x8000 <= addr <= 0xBFFF:
                bank_registers[1] = value & 0xFF
                return True
            return False
        if mapper == self.CART_MAPPER_CROSS_BLAIM:
            bank_registers[1] = value & 0x03
            return True
        if mapper == self.CART_MAPPER_RTYPE:
            if 0x4000 <= addr <= 0x7FFF:
                if value & 0x10:
                    bank_registers[1] = value & 0x17
                else:
                    bank_registers[1] = value & 0x1F
                return True
            return False
        if mapper == self.CART_MAPPER_KONAMI:
            if 0x6000 <= addr <= 0x7FFF:
                bank_registers[1] = value & 0xFF
                return True
            if 0x8000 <= addr <= 0x9FFF:
                bank_registers[2] = value & 0xFF
                return True
            if 0xA000 <= addr <= 0xBFFF:
                bank_registers[3] = value & 0xFF
                return True
            return False
        if mapper == self.CART_MAPPER_KONAMI_SCC:
            if 0x5000 <= addr <= 0x57FF:
                bank_registers[0] = value & 0xFF
                return True
            if 0x7000 <= addr <= 0x77FF:
                bank_registers[1] = value & 0xFF
                return True
            if 0x9000 <= addr <= 0x97FF:
                bank_registers[2] = value & 0xFF
                return True
            if 0xB000 <= addr <= 0xB7FF:
                bank_registers[3] = value & 0xFF
                return True
            return False
        segment = (addr - 0x4000) // self.CART_BANK_SIZE
        if not (0 <= segment < 4):
            return False
        bank_registers[segment] = value & 0xFF
        return True

    def peek(self, addr: int) -> int:
        return self.memory_map.peek(addr)

    def poke(self, addr: int, value: int) -> None:
        self.memory_map.poke(addr, value)

    def _port_read(self, port: int) -> int:
        port &= 0xFF

        if 0x98 <= port <= 0x9B:
            if port & 0x01:
                return self.vdp.read_control()
            return self.vdp.read_data()

        if 0xA0 <= port <= 0xA3:
            if (port & 0x03) == 0x02:
                return self.psg.read_selected()
            return 0xFF

        if 0xA8 <= port <= 0xAB:
            low = port & 0x03
            if low == 0:
                return self.ppi.read_port_a()
            if low == 1:
                return self.ppi.read_port_b()
            if low == 2:
                return self.ppi.read_port_c()
            return self.ppi.control & 0xFF

        return 0xFF

    def _port_write(self, port: int, value: int) -> None:
        port &= 0xFF
        value &= 0xFF

        if 0x98 <= port <= 0x9B:
            if port & 0x01:
                self.vdp.write_control(value)
            else:
                self.vdp.write_data(value)
            return

        if 0xA0 <= port <= 0xA3:
            low = port & 0x03
            if low == 0:
                self.psg.select_register(value)
            elif low == 1:
                self._flush_audio_until(self.frame_tstates)
                self.psg.write_selected(value)
            return

        if 0xA8 <= port <= 0xAB:
            low = port & 0x03
            if low == 0:
                self.ppi.write_port_a(value)
            elif low == 1:
                self.ppi.write_port_b(value)
            elif low == 2:
                self.ppi.write_port_c(value)
            else:
                self.ppi.write_control(value)

    def _read_psg_port_a(self) -> int:
        selected_port = 1 if (self.psg.registers[15] & 0x40) else 0
        return 0xC0 | (self.joystick_ports[selected_port] & 0x3F)

    def _write_psg_port_b(self, value: int) -> None:
        self.psg_port_b_output = value & 0xFF

    def clear_input_state(self):
        self.keyboard_matrix = [0xFF] * self.KEYBOARD_ROWS
        self.joystick_ports = [0x3F, 0x3F]

    def _set_joystick_control(self, player: int, bit_index: int, active: bool) -> None:
        state = self.joystick_ports[player]
        mask = 1 << bit_index
        if active:
            state &= ~mask
        else:
            state |= mask
        self.joystick_ports[player] = state & 0x3F

    def handle_input_event(self, event):
        if not isinstance(event, InputEvent):
            raise TypeError(f"evento de input inválido: {type(event)!r}")

        if event.kind == "key_matrix":
            row = int(event.control_a)
            bit = int(event.control_b)
            if not (0 <= row < self.KEYBOARD_ROWS and 0 <= bit < 8):
                return
            if event.active:
                self.keyboard_matrix[row] &= ~(1 << bit)
            else:
                self.keyboard_matrix[row] |= 1 << bit
            self.keyboard_matrix[row] &= 0xFF
            return

        if event.kind == "joystick":
            player = int(event.control_a)
            if not (0 <= player < 2):
                return
            if event.control_b & JOYSTICK_UP:
                self._set_joystick_control(player, 0, event.active)
            if event.control_b & JOYSTICK_DOWN:
                self._set_joystick_control(player, 1, event.active)
            if event.control_b & JOYSTICK_LEFT:
                self._set_joystick_control(player, 2, event.active)
            if event.control_b & JOYSTICK_RIGHT:
                self._set_joystick_control(player, 3, event.active)
            if event.control_b & JOYSTICK_FIRE:
                self._set_joystick_control(player, 4, event.active)
            if event.control_b & JOYSTICK_FIRE_2:
                self._set_joystick_control(player, 5, event.active)
            return

        raise ValueError(f"input no soportado: {event!r}")

    def debug_devices(self) -> list[dict]:
        return build_debug_devices(
            self,
            super().debug_devices(),
            [
                ("vdp", self.vdp, "video", "VDP", None),
                ("psg", self.psg, "audio", "PSG", None),
                ("ppi", self.ppi, "io", "PPI", None),
                ("ram", self._ram_debug_device, "memory", "RAM", True),
                ("bios", self._bios_debug_device, "rom", "BIOS", False),
                ("basic", self._basic_debug_device, "rom", "BASIC", False),
                ("cart1", self._cart1_debug_device, "rom", "CART1", False),
                ("cart2", self._cart2_debug_device, "rom", "CART2", False),
                ("tape", self._tape_debug_device, "tape", "CAS", False),
            ],
        )

    def read_state(self) -> dict:
        state = super().read_state()
        state |= {
            **blob_state_fields({
                "bios": self.bios_blob,
                "basic": self.basic_blob,
                "cart1": self.cart1_blob,
                "cart2": self.cart2_blob,
                "tape": self.tape_blob,
            }),
            "slot_register": self.slot_register,
            "subslot_register": self.subslot_register,
            "ram": list(self.ram),
            "keyboard_matrix": list(self.keyboard_matrix),
            "joystick_ports": list(self.joystick_ports),
            "psg_port_b_output": self.psg_port_b_output,
            "cassette_activity_frames": self._cassette_activity_frames,
            "cart1_bank_registers": list(self.cart1_bank_registers),
            "cart2_bank_registers": list(self.cart2_bank_registers),
            "cart1_mapper": self.cart1_mapper,
            "cart2_mapper": self.cart2_mapper,
            "ppi": self.ppi.read_state(),
            "vdp": self.vdp.read_state(),
            "psg": self.psg.read_state(),
        }
        if self.tape is not None:
            state["tape_device"] = self.tape.read_state()
        return state

    def write_state(self, state: dict) -> None:
        validate_state_blobs(
            state,
            context="MSX",
            blobs={
                "bios": self.bios_blob,
                "basic": self.basic_blob,
                "cart1": self.cart1_blob,
                "cart2": self.cart2_blob,
                "tape": self.tape_blob,
            },
        )
        super().write_state(state)
        if "slot_register" in state:
            self.slot_register = int(state["slot_register"]) & 0xFF
        if "subslot_register" in state:
            self.subslot_register = int(state["subslot_register"]) & 0xFF
        if "ram" in state:
            restore_byte_array_state(self.ram, state["ram"], label="RAM MSX")
        if "keyboard_matrix" in state:
            self.keyboard_matrix = restore_fixed_length_list(
                state["keyboard_matrix"],
                length=self.KEYBOARD_ROWS,
                mask=0xFF,
                fill=0xFF,
            )
        if "joystick_ports" in state:
            restored = restore_fixed_length_list(
                state["joystick_ports"],
                length=2,
                mask=0x3F,
                fill=0x3F,
            )
            self.joystick_ports = restored
        if "cart1_bank_registers" in state:
            self.cart1_bank_registers = restore_fixed_length_list(
                state["cart1_bank_registers"],
                length=4,
                mask=0xFF,
                fill=0x00,
            )
        if "cart2_bank_registers" in state:
            self.cart2_bank_registers = restore_fixed_length_list(
                state["cart2_bank_registers"],
                length=4,
                mask=0xFF,
                fill=0x00,
            )
        if "cart1_mapper" in state:
            self.cart1_mapper = str(state["cart1_mapper"])
        if "cart2_mapper" in state:
            self.cart2_mapper = str(state["cart2_mapper"])
        if "psg_port_b_output" in state:
            self.psg_port_b_output = int(state["psg_port_b_output"]) & 0xFF
        if "cassette_activity_frames" in state:
            self._cassette_activity_frames = max(0, int(state["cassette_activity_frames"]))
        if "ppi" in state:
            self.ppi.write_state(state["ppi"])
        if "vdp" in state:
            self.vdp.write_state(state["vdp"])
            self.framebuffer_rgb24 = self.vdp.framebuffer_rgb24
        if "psg" in state:
            self.psg.write_state(state["psg"])
        if self.tape is not None and "tape_device" in state:
            self.tape.write_state(state["tape_device"])
