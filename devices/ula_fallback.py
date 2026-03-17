from __future__ import annotations

from array import array


class ULABeeper:
    def __init__(
        self,
        ula,
        *,
        sample_rate: int = 44100,
        amplitude: int = 6000,
        tstates_per_frame: int = 69888,
    ):
        self.ula = ula
        self.machine = ula.machine
        self.sample_rate = sample_rate
        self.amplitude = amplitude
        self.tstates_per_frame = tstates_per_frame

        self.tstates_per_second = self.tstates_per_frame * 50
        self.samples_per_frame = int(round(sample_rate / 50.0))

        self.current_level = 0
        self.start_level = 0
        self.events: list[tuple[int, int]] = []
        self.frame_start_tstate = 0
        self.total_tstates = 0
        self.total_samples_emitted = 0
        self.filter_state_1 = 0.0
        self.filter_state_2 = 0.0
        self.frame_samples = array("h", [0] * self.samples_per_frame)

    def reset(self):
        self.current_level = 0
        self.start_level = 0
        self.events = []
        self.frame_start_tstate = 0
        self.total_tstates = 0
        self.total_samples_emitted = 0
        self.filter_state_1 = 0.0
        self.filter_state_2 = 0.0
        self.frame_samples = array("h", [0] * self.samples_per_frame)

    def begin_frame(self):
        self.start_level = self.current_level
        self.events = []
        self.frame_start_tstate = self.total_tstates

    def run_until(self, tstates: int):
        _ = tstates

    def set_level_from_port_value(self, value: int, tstate_in_frame: int):
        new_level = 1 if (value & 0x10) else 0

        if new_level != self.current_level:
            if tstate_in_frame < 0:
                tstate_in_frame = 0
            elif tstate_in_frame > self.tstates_per_frame:
                tstate_in_frame = self.tstates_per_frame

            self.events.append((self.frame_start_tstate + tstate_in_frame, new_level))
            self.current_level = new_level

    def end_frame(self):
        self.total_tstates += self.tstates_per_frame
        self.frame_samples = self._render_frame_samples()

    def get_frame_samples(self) -> array:
        return self.frame_samples

    def _render_frame_samples(self) -> array:
        frame_start_sample = self.total_samples_emitted
        frame_end_sample = (self.total_tstates * self.sample_rate) // self.tstates_per_second
        sample_count = frame_end_sample - frame_start_sample

        if sample_count <= 0:
            return array("h")

        out = array("h", [0] * sample_count)
        events = sorted(self.events, key=lambda event: event[0])
        level = self.start_level
        event_idx = 0

        for i in range(sample_count):
            abs_sample_idx = frame_start_sample + i
            sample_start_tstate = (abs_sample_idx * self.tstates_per_second) // self.sample_rate
            sample_end_tstate = (
                ((abs_sample_idx + 1) * self.tstates_per_second) // self.sample_rate
            )

            if sample_end_tstate <= sample_start_tstate:
                sample_value = self.amplitude if level else -self.amplitude
            else:
                accum = 0
                current_tstate = sample_start_tstate

                while event_idx < len(events) and events[event_idx][0] < sample_end_tstate:
                    event_tstate, new_level = events[event_idx]
                    if event_tstate > current_tstate:
                        accum += (event_tstate - current_tstate) * (
                            self.amplitude if level else -self.amplitude
                        )
                    current_tstate = event_tstate
                    level = new_level
                    event_idx += 1

                if sample_end_tstate > current_tstate:
                    accum += (sample_end_tstate - current_tstate) * (
                        self.amplitude if level else -self.amplitude
                    )

                sample_value = accum // (sample_end_tstate - sample_start_tstate)

            self.filter_state_1 += (sample_value - self.filter_state_1) * 0.45
            self.filter_state_2 += (self.filter_state_1 - self.filter_state_2) * 0.2
            out[i] = int(self.filter_state_2)

        self.total_samples_emitted = frame_end_sample
        return out


class Spectrum48KULA:
    SCREEN_WIDTH = 256
    SCREEN_HEIGHT = 192

    BORDER_LEFT = 48
    BORDER_RIGHT = 48
    BORDER_TOP = 48
    BORDER_BOTTOM = 56

    FRAME_WIDTH = SCREEN_WIDTH + BORDER_LEFT + BORDER_RIGHT
    FRAME_HEIGHT = SCREEN_HEIGHT + BORDER_TOP + BORDER_BOTTOM

    SCREEN_BITMAP_BASE = 0x4000
    SCREEN_ATTR_BASE = 0x5800

    PALETTE = [
        (0, 0, 0),
        (0, 0, 205),
        (205, 0, 0),
        (205, 0, 205),
        (0, 205, 0),
        (0, 205, 205),
        (205, 205, 0),
        (205, 205, 205),
        (0, 0, 0),
        (0, 0, 255),
        (255, 0, 0),
        (255, 0, 255),
        (0, 255, 0),
        (0, 255, 255),
        (255, 255, 0),
        (255, 255, 255),
    ]

    def __init__(self, machine):
        self.machine = machine
        self.last_tstates = 0
        self.flash_phase = False
        self.flash_counter = 0

        self.framebuffer = self._make_blank_frame((0, 0, 0))
        self.beeper = ULABeeper(self, tstates_per_frame=machine.TSTATES_PER_FRAME)

    def reset(self):
        self.last_tstates = 0
        self.flash_phase = False
        self.flash_counter = 0
        self.framebuffer = self._make_blank_frame((0, 0, 0))
        self.beeper.reset()

    def run_until(self, tstates: int):
        self.last_tstates = tstates
        self.beeper.run_until(tstates)

    def end_frame(self):
        self.flash_counter += 1
        if self.flash_counter >= 16:
            self.flash_counter = 0
            self.flash_phase = not self.flash_phase

        self.machine.cpu.interrupt()
        self.framebuffer = self.render_frame()
        self.beeper.end_frame()

    def render_frame(self):
        border_rgb = self.PALETTE[self.machine.border_color & 0x07]
        frame = self._make_blank_frame(border_rgb)

        for y in range(self.SCREEN_HEIGHT):
            bitmap_row_addr = self._zx_bitmap_row_address(y)
            attr_row_addr = self.SCREEN_ATTR_BASE + ((y >> 3) * 32)
            dst_y = self.BORDER_TOP + y

            for x_char in range(32):
                bitmap_byte = self.machine.peek(bitmap_row_addr + x_char)
                attr = self.machine.peek(attr_row_addr + x_char)

                ink, paper = self._decode_attr(attr)
                dst_x_base = self.BORDER_LEFT + (x_char * 8)

                for bit in range(8):
                    pixel_on = (bitmap_byte >> (7 - bit)) & 1
                    rgb = ink if pixel_on else paper
                    frame[dst_y][dst_x_base + bit] = rgb

        return frame

    def get_frame_samples(self):
        return self.beeper.get_frame_samples()

    def _decode_attr(self, attr: int):
        ink = attr & 0x07
        paper = (attr >> 3) & 0x07
        bright = (attr >> 6) & 0x01
        flash = (attr >> 7) & 0x01

        if bright:
            ink += 8
            paper += 8

        if flash and self.flash_phase:
            ink, paper = paper, ink

        return self.PALETTE[ink], self.PALETTE[paper]

    def _zx_bitmap_row_address(self, y: int) -> int:
        return (
            self.SCREEN_BITMAP_BASE
            + ((y & 0xC0) << 5)
            + ((y & 0x07) << 8)
            + ((y & 0x38) << 2)
        )

    def _make_blank_frame(self, rgb):
        return [
            [rgb for _ in range(self.FRAME_WIDTH)]
            for _ in range(self.FRAME_HEIGHT)
        ]
