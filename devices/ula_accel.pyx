# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False
# cython: cdivision=True

from array import array

from cpu.z80.memory cimport RAMBlock


cdef class ULABeeper:
    cdef public object ula
    cdef public object machine
    cdef public int sample_rate
    cdef public int amplitude
    cdef public int tstates_per_frame
    cdef public int tstates_per_second
    cdef public int samples_per_frame
    cdef public int current_level
    cdef public int start_level
    cdef public list events
    cdef public long long frame_start_tstate
    cdef public long long total_tstates
    cdef public long long total_samples_emitted
    cdef public double filter_state_1
    cdef public double filter_state_2
    cdef public object frame_samples

    def __init__(
        self,
        ula,
        *,
        int sample_rate=44100,
        int amplitude=6000,
        int tstates_per_frame=69888,
    ):
        self.ula = ula
        self.machine = ula.machine
        self.sample_rate = sample_rate
        self.amplitude = amplitude
        self.tstates_per_frame = tstates_per_frame

        self.tstates_per_second = self.tstates_per_frame * 50
        self.samples_per_frame = <int>round(sample_rate / 50.0)

        self.current_level = 0
        self.start_level = 0
        self.events = []
        self.frame_start_tstate = 0
        self.total_tstates = 0
        self.total_samples_emitted = 0
        self.filter_state_1 = 0.0
        self.filter_state_2 = 0.0
        self.frame_samples = array("h", [0] * self.samples_per_frame)

    cpdef reset(self):
        self.current_level = 0
        self.start_level = 0
        self.events = []
        self.frame_start_tstate = 0
        self.total_tstates = 0
        self.total_samples_emitted = 0
        self.filter_state_1 = 0.0
        self.filter_state_2 = 0.0
        self.frame_samples = array("h", [0] * self.samples_per_frame)

    cpdef begin_frame(self):
        self.start_level = self.current_level
        self.events = []
        self.frame_start_tstate = self.total_tstates

    cpdef run_until(self, int tstates):
        _ = tstates

    cpdef set_level_from_port_value(self, int value, int tstate_in_frame):
        cdef int new_level = 1 if (value & 0x10) else 0

        if new_level != self.current_level:
            if tstate_in_frame < 0:
                tstate_in_frame = 0
            elif tstate_in_frame > self.tstates_per_frame:
                tstate_in_frame = self.tstates_per_frame

            self.events.append((self.frame_start_tstate + tstate_in_frame, new_level))
            self.current_level = new_level

    cpdef end_frame(self):
        self.total_tstates += self.tstates_per_frame
        self.frame_samples = self._render_frame_samples()

    cpdef get_frame_samples(self):
        return self.frame_samples

    cdef object _render_frame_samples(self):
        cdef long long frame_start_sample = self.total_samples_emitted
        cdef long long frame_end_sample = (
            self.total_tstates * self.sample_rate
        ) // self.tstates_per_second
        cdef int sample_count = <int>(frame_end_sample - frame_start_sample)
        cdef object out
        cdef list events
        cdef int level
        cdef int event_idx
        cdef int i
        cdef long long abs_sample_idx
        cdef long long sample_start_tstate
        cdef long long sample_end_tstate
        cdef int sample_value
        cdef long long accum
        cdef long long current_tstate
        cdef long long event_tstate
        cdef int new_level
        cdef tuple event

        if sample_count <= 0:
            return array("h")

        out = array("h", [0] * sample_count)
        events = sorted(self.events, key=lambda event: event[0])
        level = self.start_level
        event_idx = 0

        for i in range(sample_count):
            abs_sample_idx = frame_start_sample + i
            sample_start_tstate = (
                abs_sample_idx * self.tstates_per_second
            ) // self.sample_rate
            sample_end_tstate = (
                (abs_sample_idx + 1) * self.tstates_per_second
            ) // self.sample_rate

            if sample_end_tstate <= sample_start_tstate:
                sample_value = self.amplitude if level else -self.amplitude
            else:
                accum = 0
                current_tstate = sample_start_tstate

                while event_idx < len(events):
                    event = events[event_idx]
                    event_tstate = <long long>event[0]
                    if event_tstate >= sample_end_tstate:
                        break

                    new_level = <int>event[1]
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


cdef class Spectrum48KULA:
    cdef public object machine
    cdef RAMBlock ram
    cdef public int last_tstates
    cdef public bint flash_phase
    cdef public int flash_counter
    cdef public object framebuffer
    cdef public ULABeeper beeper

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

    PALETTE = (
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
    )

    def __init__(self, machine):
        self.machine = machine
        self.ram = <RAMBlock>machine.ram
        self.last_tstates = 0
        self.flash_phase = False
        self.flash_counter = 0

        self.framebuffer = self._make_blank_frame((0, 0, 0))
        self.beeper = ULABeeper(self, tstates_per_frame=machine.TSTATES_PER_FRAME)

    cpdef reset(self):
        self.last_tstates = 0
        self.flash_phase = False
        self.flash_counter = 0
        self.framebuffer = self._make_blank_frame((0, 0, 0))
        self.beeper.reset()

    cpdef run_until(self, int tstates):
        self.last_tstates = tstates
        self.beeper.run_until(tstates)

    cpdef end_frame(self):
        self.flash_counter += 1
        if self.flash_counter >= 16:
            self.flash_counter = 0
            self.flash_phase = not self.flash_phase

        self.machine.cpu.interrupt()
        self.framebuffer = self.render_frame()
        self.beeper.end_frame()

    cpdef render_frame(self):
        cdef int border_index = self.machine.border_color & 0x07
        cdef list frame = self._make_blank_frame(self.PALETTE[border_index])
        cdef int y
        cdef int bitmap_row_addr
        cdef int attr_row_addr
        cdef int dst_y
        cdef int x_char
        cdef int bitmap_byte
        cdef int attr
        cdef int ink_idx
        cdef int paper_idx
        cdef int dst_x_base
        cdef int bit
        cdef int pixel_on
        cdef list frame_row
        cdef object ink_rgb
        cdef object paper_rgb
        cdef object tmp

        for y in range(self.SCREEN_HEIGHT):
            bitmap_row_addr = self._zx_bitmap_row_address(y) - 0x4000
            attr_row_addr = self.SCREEN_ATTR_BASE + ((y >> 3) * 32) - 0x4000
            dst_y = self.BORDER_TOP + y
            frame_row = frame[dst_y]

            for x_char in range(32):
                bitmap_byte = self.ram.data[bitmap_row_addr + x_char]
                attr = self.ram.data[attr_row_addr + x_char]

                ink_idx = attr & 0x07
                paper_idx = (attr >> 3) & 0x07

                if attr & 0x40:
                    ink_idx += 8
                    paper_idx += 8

                if (attr & 0x80) and self.flash_phase:
                    tmp = ink_idx
                    ink_idx = paper_idx
                    paper_idx = <int>tmp

                ink_rgb = self.PALETTE[ink_idx]
                paper_rgb = self.PALETTE[paper_idx]
                dst_x_base = self.BORDER_LEFT + (x_char * 8)

                for bit in range(8):
                    pixel_on = (bitmap_byte >> (7 - bit)) & 1
                    frame_row[dst_x_base + bit] = ink_rgb if pixel_on else paper_rgb

        return frame

    cpdef get_frame_samples(self):
        return self.beeper.get_frame_samples()

    cdef inline int _zx_bitmap_row_address(self, int y):
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
