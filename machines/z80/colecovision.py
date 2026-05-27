from __future__ import annotations

from array import array

from cpu.z80 import MemoryDevice, ROMBlock, Z80Bus, Z80Core
from chipsets import SN76489, TMS9918A
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
from machines.common import (
    ByteArrayMemoryDebugDevice,
    ReadOnlyBlobDebugDevice,
    blob_state_fields,
    build_debug_devices,
    pad_rom,
    restore_byte_array_state,
    validate_state_blobs,
)
from machines.frame_runner import SteppedFrameRunner
from machines.z80.common import install_uniform_port_handlers


def _normalize_cart_signature(cart_data: bytes) -> bytes:
    if len(cart_data) >= 2 and cart_data[:2] == b"\xAA\x55":
        return b"\x55\xAA" + cart_data[2:]
    return cart_data


class ColecoVisionRAM(MemoryDevice):
    """Expose the 1KB ColecoVision RAM mirrored across 0x6000-0x7FFF."""

    def __init__(self, machine: "ColecoVision"):
        self.machine = machine

    def read(self, addr):
        return self.machine.ram[addr & 0x03FF]

    def write(self, addr, value):
        self.machine.ram[addr & 0x03FF] = value & 0xFF


class ColecoVision(BaseMachine):
    """ColecoVision: Z80 + BIOS/cart + RAM + SN76489 + TMS9918A."""

    CPU_CLOCK_HZ = 3_579_545
    PSG_CLOCK_HZ = CPU_CLOCK_HZ
    FRAMES_PER_SECOND = 60
    TSTATES_PER_FRAME = 59_659
    AUDIO_FRAMES_PER_SECOND = CPU_CLOCK_HZ / TSTATES_PER_FRAME
    TARGET_FPS = AUDIO_FRAMES_PER_SECOND
    PSG_OVERSAMPLE = 8
    PSG_WRITE_WAIT_TSTATES = 32
    IO_WAIT_TSTATES = 1
    LOW_MEM_WAIT_TSTATES = 1
    AUDIO_CHANNELS = 1

    SCREEN_WIDTH = 256
    SCREEN_HEIGHT = 192
    BIOS_SIZE = 0x2000
    CART_SIZE = 0x8000
    RAM_SIZE = 0x0400

    input_keymap_name = "colecovision"
    input_gamepad_map_name = "colecovision"
    input_joystick_count = 1
    vdp_vblank_uses_nmi = True

    @property
    def _pad1_state(self) -> int:
        return self._joystick_state

    @_pad1_state.setter
    def _pad1_state(self, value: int) -> None:
        self._joystick_state = int(value) & 0xFF

    def __init__(
        self,
        cart_data: bytes | None = None,
        *,
        bios_data: bytes | None = None,
        display_profile: str = "default",
        audio_sample_rate: int = 44100,
    ):
        bus = Z80Bus()
        bus.wait_io_tstates = self.IO_WAIT_TSTATES
        bus.wait_low_mem_tstates = self.LOW_MEM_WAIT_TSTATES
        cpu = Z80Core(bus)
        cpu.m1_wait_tstates = 1
        super().__init__(bus=bus, cpu=cpu, audio_sample_rate=audio_sample_rate)

        if bios_data is None:
            raise ValueError("ColecoVision requiere BIOS")
        if cart_data is None and bios_data is None:
            raise ValueError("ColecoVision requiere BIOS o cartucho")

        self.machine_id = "colecovision"
        self.display_name = "ColecoVision"
        self.display_profile_name = display_profile

        self.bios_data = pad_rom(bytes(bios_data), self.BIOS_SIZE)
        self.cart_data = pad_rom(_normalize_cart_signature(bytes(cart_data or b"")), self.CART_SIZE)
        self.ram = bytearray(self.RAM_SIZE)

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
        self._pending_wait_tstates = 0

        self._controller_mode = "joystick"
        self._joystick_state = 0xFF
        self._keypad_code = None

        self.psg = SN76489(
            clock_hz=self.PSG_CLOCK_HZ,
            sample_rate=self.audio_internal_sample_rate,
        )
        self.vdp = TMS9918A(self)
        self._bios_debug_device = ReadOnlyBlobDebugDevice(
            self,
            attr_name="bios_data",
            meta_type="ColecoVisionBIOS",
        )
        self._cart_debug_device = ReadOnlyBlobDebugDevice(
            self,
            attr_name="cart_data",
            meta_type="ColecoVisionCartridge",
        )
        self._ram_debug_device = ByteArrayMemoryDebugDevice(
            self,
            attr_name="ram",
            size=self.RAM_SIZE,
            meta_type="ColecoVisionRAM",
        )
        self.framebuffer_rgb24 = self.vdp.framebuffer_rgb24

        self._bios = ROMBlock(self.BIOS_SIZE)
        self._bios.load_bytes(self.bios_data)
        self._cart = ROMBlock(self.CART_SIZE)
        self._cart.load_bytes(self.cart_data)
        self._ram_map = ColecoVisionRAM(self)

        self.bus.map_block(0x0000, self._bios)
        self.bus.map_device(0x6000, 0x2000, self._ram_map)
        self.bus.map_block(0x8000, self._cart)
        install_uniform_port_handlers(self.bus, self._port_read, self._port_write)

        self._frame_runner = SteppedFrameRunner(self.TSTATES_PER_FRAME)

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

    def run_frame(self) -> int:
        self._frame_runner.run(
            self,
            self._cpu_step_with_wait,
            self._run_devices_until,
            self._begin_frame,
            self._finish_frame,
        )
        return self.tstates

    def _cpu_step_with_wait(self) -> int:
        used = int(self.cpu.step())
        if self._pending_wait_tstates:
            used += self._pending_wait_tstates
            self._pending_wait_tstates = 0
        return used

    def render_frame(self):
        return self.framebuffer_rgb24

    def _run_devices_until(self, tstates: int):
        self.vdp.run_until(tstates)
        self._flush_audio_until(tstates)

    def peek(self, addr: int) -> int:
        addr &= 0xFFFF
        if addr < 0x2000:
            return self.bios_data[addr]
        if 0x6000 <= addr < 0x8000:
            return self.ram[addr & 0x03FF]
        if addr >= 0x8000:
            return self.cart_data[addr - 0x8000]
        return 0xFF

    def poke(self, addr: int, value: int) -> None:
        addr &= 0xFFFF
        value &= 0xFF
        if 0x6000 <= addr < 0x8000:
            self.ram[addr & 0x03FF] = value

    def _flush_audio_until(self, tstates: int) -> None:
        target_samples = (
            max(0, min(self.TSTATES_PER_FRAME, tstates)) * self._current_frame_internal_sample_target
        ) // self.TSTATES_PER_FRAME
        delta_samples = target_samples - self._audio_rendered_samples
        if delta_samples > 0:
            self._frame_audio.extend(self.psg.render_samples(delta_samples))
            self._audio_rendered_samples = target_samples

    def _downsample_audio_frame(self, samples: array, output_count: int) -> array:
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

    def _port_read(self, port: int) -> int:
        port &= 0xFF
        if 0xE0 <= port <= 0xFF:
            return self._controller_port_value()
        if 0xA0 <= port <= 0xBF:
            if port & 0x01:
                return self.vdp.read_control()
            return self.vdp.read_data()
        return 0xFF

    def _port_write(self, port: int, value: int) -> None:
        port &= 0xFF
        value &= 0xFF
        if 0x80 <= port <= 0x9F:
            self._controller_mode = "keypad"
            return
        if 0xC0 <= port <= 0xDF:
            self._controller_mode = "joystick"
            return
        if 0xA0 <= port <= 0xBF:
            if port & 0x01:
                self.vdp.write_control(value)
            else:
                self.vdp.write_data(value)
            return
        if 0xE0 <= port <= 0xFF:
            self._flush_audio_until(self.frame_tstates)
            self.psg.write(value)
            self._pending_wait_tstates += self.PSG_WRITE_WAIT_TSTATES
            return

    def clear_input_state(self):
        self._joystick_state = 0xFF
        self._keypad_code = None

    def _set_pad_control(self, group: int, bit: int, active: bool) -> None:
        if group != 1:
            return
        mask_by_bit = {
            0: JOYSTICK_UP,
            1: JOYSTICK_DOWN,
            2: JOYSTICK_LEFT,
            3: JOYSTICK_RIGHT,
            4: JOYSTICK_FIRE,
            5: JOYSTICK_FIRE_2,
            6: JOYSTICK_START,
        }
        mask = mask_by_bit.get(bit)
        if mask is None:
            return
        if active:
            self._joystick_state &= ~mask
        else:
            self._joystick_state |= mask
        self._joystick_state &= 0xFF

    def _set_keypad_key(self, key: int, active: bool) -> None:
        if active:
            self._keypad_code = key & 0x0F
        elif self._keypad_code == (key & 0x0F):
            self._keypad_code = None

    def _controller_port_value(self) -> int:
        if self._controller_mode == "keypad":
            return self._keypad_port_value()
        return self._joystick_port_value()

    def _joystick_port_value(self) -> int:
        value = 0xFF
        if (self._joystick_state & JOYSTICK_UP) == 0:
            value &= ~0x01
        if (self._joystick_state & JOYSTICK_RIGHT) == 0:
            value &= ~0x02
        if (self._joystick_state & JOYSTICK_DOWN) == 0:
            value &= ~0x04
        if (self._joystick_state & JOYSTICK_LEFT) == 0:
            value &= ~0x08
        if (self._joystick_state & JOYSTICK_FIRE) == 0:
            value &= ~0x40
        return value & 0xFF

    def _keypad_port_value(self) -> int:
        value = 0xFF
        keypad_bits = {
            0: 0x0A,
            1: 0x0D,
            2: 0x07,
            3: 0x0C,
            4: 0x02,
            5: 0x03,
            6: 0x0E,
            7: 0x05,
            8: 0x01,
            9: 0x0B,
            10: 0x09,
            11: 0x06,
        }
        if self._keypad_code is not None:
            value = (value & 0xF0) | (keypad_bits.get(self._keypad_code, 0x0F) & 0x0F)
        if (self._joystick_state & JOYSTICK_FIRE_2) == 0:
            value &= ~0x40
        return value & 0xFF

    def handle_input_event(self, event):
        if event.kind == "key_matrix":
            if event.control_a == 0:
                self._set_pad_control(1, event.control_b, event.active)
                return
            if event.control_a == 1:
                self._set_keypad_key(event.control_b, event.active)
                return
            return
        if event.kind == "joystick":
            mask_by_control = {
                JOYSTICK_UP: 0,
                JOYSTICK_DOWN: 1,
                JOYSTICK_LEFT: 2,
                JOYSTICK_RIGHT: 3,
                JOYSTICK_FIRE: 4,
                JOYSTICK_FIRE_2: 5,
                JOYSTICK_START: 6,
            }
            bit = mask_by_control.get(event.control_b)
            if bit is None:
                return
            self._set_pad_control(1, bit, event.active)
            return
        raise ValueError(f"input no soportado: {event!r}")

    def reset(self):
        super().reset()
        self.ram[:] = b"\x00" * self.RAM_SIZE
        self._joystick_state = 0xFF
        self._keypad_code = None
        self._controller_mode = "joystick"
        self._audio_sample_fraction = 0.0
        self._frame_audio = array("h")
        self._audio_rendered_samples = 0
        self._current_frame_sample_target = self.samples_per_frame
        self._current_frame_internal_sample_target = self.samples_per_frame * self.PSG_OVERSAMPLE
        self._pending_wait_tstates = 0
        self.psg.reset()
        self.vdp.reset()
        self.framebuffer_rgb24 = self.vdp.framebuffer_rgb24

    def snapshot(self) -> dict:
        snap = self.cpu.snapshot()
        snap["joystick_state"] = self._joystick_state
        snap["keypad_code"] = self._keypad_code
        snap["controller_mode"] = self._controller_mode
        snap["frame_counter"] = self.frame_counter
        snap["frame_tstates"] = self.frame_tstates
        snap["tstates"] = self.tstates
        snap["pending_wait_tstates"] = self._pending_wait_tstates
        return snap

    def debug_devices(self) -> list[dict]:
        return build_debug_devices(
            self,
            super().debug_devices(),
            [
                ("bios", self._bios_debug_device, "memory", "BIOS ROM", False),
                ("cartridge", self._cart_debug_device, "memory", "Cartridge ROM", False),
                ("ram", self._ram_debug_device, "memory", "System RAM", None),
                ("vdp", self.vdp, "chip", "TMS9918A", None),
                ("psg", self.psg, "chip", "PSG", None),
            ],
        )

    def read_state(self) -> dict:
        state = super().read_state()
        state |= {
            "__meta__": {
                "type": type(self).__name__,
                "module": type(self).__module__,
            },
            "ram": list(self.ram),
            "joystick_state": self._joystick_state,
            "keypad_code": self._keypad_code,
            "controller_mode": self._controller_mode,
            "pending_wait_tstates": self._pending_wait_tstates,
            "vdp": self.vdp.read_state(),
            "psg": self.psg.read_state(),
        }
        state.update(blob_state_fields({"bios": self.bios_data, "cart": self.cart_data}))
        return state

    def write_state(self, state: dict) -> None:
        super().write_state(state)
        validate_state_blobs(
            state,
            context="ColecoVision",
            blobs={
                "bios": self.bios_data,
                "cart": self.cart_data,
            },
        )
        if "ram" in state:
            restore_byte_array_state(self.ram, state["ram"], label="RAM de ColecoVision")
        if "joystick_state" in state:
            self._joystick_state = int(state["joystick_state"]) & 0xFF
        if "keypad_code" in state:
            value = state["keypad_code"]
            self._keypad_code = None if value is None else (int(value) & 0x0F)
        if "controller_mode" in state:
            self._controller_mode = str(state["controller_mode"])
        if "pending_wait_tstates" in state:
            self._pending_wait_tstates = int(state["pending_wait_tstates"])
        if "vdp" in state:
            self.vdp.write_state(state["vdp"])
        if "psg" in state:
            self.psg.write_state(state["psg"])
        self.framebuffer_rgb24 = self.vdp.framebuffer_rgb24
