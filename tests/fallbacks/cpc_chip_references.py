from __future__ import annotations


class CPCGateArray:
    """Reference pure-Python Gate Array kept only for tests."""

    HARDWARE_PALETTE = (
        (255, 255, 255),
        (255, 255, 255),
        (0, 128, 128),
        (255, 255, 128),
        (0, 0, 128),
        (128, 0, 128),
        (0, 255, 255),
        (255, 128, 192),
        (128, 0, 128),
        (255, 255, 128),
        (255, 255, 0),
        (255, 255, 255),
        (255, 0, 0),
        (255, 0, 255),
        (255, 128, 0),
        (255, 128, 255),
        (0, 0, 128),
        (0, 128, 128),
        (0, 255, 0),
        (0, 255, 255),
        (0, 0, 0),
        (0, 0, 255),
        (0, 128, 0),
        (128, 192, 255),
        (255, 0, 255),
        (128, 255, 128),
        (128, 255, 0),
        (128, 255, 255),
        (128, 0, 0),
        (128, 0, 255),
        (255, 255, 0),
        (128, 128, 255),
    )

    def __init__(self, machine):
        self.machine = machine
        self.selected_pen = 0
        self.border_hardware_color = 20
        self.pen_colors = [20] * 16
        self.mode = 1
        self.interrupt_line_counter = 0
        self.pending_interrupt = False
        self._last_vsync_active = False
        self._vsync_delay_lines = 0

    def reset(self) -> None:
        self.selected_pen = 0
        self.border_hardware_color = 20
        self.pen_colors = [20] * 16
        self.mode = 1
        self.interrupt_line_counter = 0
        self.pending_interrupt = False
        self._last_vsync_active = False
        self._vsync_delay_lines = 0
        self.machine.set_rom_configuration(
            lower_rom_enabled=True,
            upper_rom_enabled=self.machine._has_upper_rom,
        )

    def write(self, value: int) -> None:
        value &= 0xFF
        command = (value >> 6) & 0b11
        if command == 0b00:
            self._select_pen(value)
            return
        if command == 0b01:
            self._select_colour(value)
            return
        if command == 0b10:
            self._select_mode_and_roms(value)

    def _select_pen(self, value: int) -> None:
        if value & 0x10:
            self.selected_pen = -1
            return
        self.selected_pen = value & 0x0F

    def _select_colour(self, value: int) -> None:
        hardware_color = value & 0x1F
        if self.selected_pen < 0:
            self.border_hardware_color = hardware_color
            self.machine.frame_border_hardware_color = hardware_color
            return
        self.pen_colors[self.selected_pen] = hardware_color

    def _select_mode_and_roms(self, value: int) -> None:
        self.mode = value & 0x03
        self.machine.frame_gate_mode = self.mode
        if value & 0x10:
            self.interrupt_line_counter = 0
        self.machine.set_rom_configuration(
            lower_rom_enabled=(value & 0x04) == 0,
            upper_rom_enabled=(value & 0x08) == 0,
        )

    def get_border_rgb(self) -> tuple[int, int, int]:
        return self.HARDWARE_PALETTE[self.border_hardware_color]

    def get_pen_rgb(self, pen: int) -> tuple[int, int, int]:
        return self.HARDWARE_PALETTE[self.pen_colors[pen & 0x0F]]

    def begin_scanline(self, vsync_active: bool) -> None:
        if vsync_active and not self._last_vsync_active:
            self._vsync_delay_lines = 2
        self._last_vsync_active = vsync_active

    def end_scanline(self) -> None:
        self.interrupt_line_counter += 1
        if self.interrupt_line_counter >= self.machine.INTERRUPT_PERIOD_LINES:
            self.pending_interrupt = True
            self.interrupt_line_counter = 0

        if self._vsync_delay_lines > 0:
            self._vsync_delay_lines -= 1
            if self._vsync_delay_lines == 0:
                if self.interrupt_line_counter >= 32:
                    self.pending_interrupt = True
                self.interrupt_line_counter = 0

    def pop_pending_interrupt(self) -> bool:
        pending = self.pending_interrupt
        self.pending_interrupt = False
        return pending

    def acknowledge_interrupt(self) -> None:
        self.interrupt_line_counter &= 0x1F


class HD6845:
    """Reference pure-Python HD6845 kept only for tests."""

    DEFAULT_REGISTERS = (
        63, 40, 46, 0x8E, 38, 0, 25, 30, 0, 7, 0, 0, 0x30, 0x00, 0, 0, 0, 0,
    )
    REGISTER_COUNT = 18

    def __init__(self):
        self.selected_register = 0
        self.registers = list(self.DEFAULT_REGISTERS)

    def reset(self) -> None:
        self.selected_register = 0
        self.registers[:] = self.DEFAULT_REGISTERS

    def select_register(self, register_index: int) -> None:
        self.selected_register = register_index & 0x1F

    def write_selected(self, value: int) -> None:
        if self.selected_register < self.REGISTER_COUNT:
            self.registers[self.selected_register] = value & 0xFF

    @property
    def horizontal_total(self) -> int:
        return max(1, self.registers[0] + 1)

    @property
    def horizontal_displayed(self) -> int:
        return max(1, self.registers[1])

    @property
    def horizontal_sync_position(self) -> int:
        return self.registers[2]

    @property
    def horizontal_sync_width(self) -> int:
        width = self.registers[3] & 0x0F
        return width or 16

    @property
    def vertical_total(self) -> int:
        return max(1, self.registers[4] + 1)

    @property
    def vertical_total_adjust(self) -> int:
        return self.registers[5] & 0x1F

    @property
    def vertical_displayed(self) -> int:
        return max(1, self.registers[6])

    @property
    def vertical_sync_position(self) -> int:
        return self.registers[7]

    @property
    def vertical_sync_width(self) -> int:
        width = (self.registers[3] >> 4) & 0x0F
        return width or 16

    @property
    def maximum_raster_address(self) -> int:
        return self.registers[9] & 0x1F

    @property
    def raster_height(self) -> int:
        return self.maximum_raster_address + 1

    @property
    def total_scanlines(self) -> int:
        return (self.vertical_total * self.raster_height) + self.vertical_total_adjust

    @property
    def display_start_address(self) -> int:
        return ((self.registers[12] << 8) | self.registers[13]) & 0x3FFF


class Intel8255:
    """Reference pure-Python Intel 8255 kept only for tests."""

    DEFAULT_CONTROL = 0x82
    DEFAULT_PORT_B = 0xDE

    def __init__(self, machine):
        self.machine = machine
        self.control = self.DEFAULT_CONTROL
        self.port_a_latch = 0
        self.port_b_latch = 0
        self.port_c_latch = 0
        self.last_port_a_read = 0xFF
        self.last_port_a_write = 0x00
        self.last_control_write = self.DEFAULT_CONTROL
        self.port_a_input = False
        self.port_b_input = True
        self.port_c_upper_input = False
        self.port_c_lower_input = False

    @property
    def selected_keyboard_line(self) -> int:
        return self.port_c_latch & 0x0F

    @property
    def psg_function(self) -> int:
        return (self.port_c_latch >> 6) & 0b11

    def reset(self) -> None:
        self.control = self.DEFAULT_CONTROL
        self.port_a_latch = 0
        self.port_b_latch = 0
        self.port_c_latch = 0
        self.last_port_a_read = 0xFF
        self.last_port_a_write = 0x00
        self.last_control_write = self.DEFAULT_CONTROL
        self.port_a_input = False
        self.port_b_input = True
        self.port_c_upper_input = False
        self.port_c_lower_input = False

    def write_port_a(self, value: int) -> None:
        self.port_a_latch = value & 0xFF
        self.last_port_a_write = self.port_a_latch
        self.machine._apply_psg_bus_control()

    def read_port_a(self) -> int:
        if self.port_a_input and self.psg_function == 0b01:
            self.last_port_a_read = self.machine.psg.read_selected()
            return self.last_port_a_read
        self.last_port_a_read = self.port_a_latch if not self.port_a_input else 0xFF
        return self.last_port_a_read

    def write_port_b(self, value: int) -> None:
        self.port_b_latch = value & 0xFF

    def read_port_b(self) -> int:
        if self.port_b_input:
            base = self.DEFAULT_PORT_B & 0xFE
            if self.machine.read_cassette_input():
                base |= 0x80
            else:
                base &= 0x7F
            return base | (1 if self.machine.vsync_active else 0)
        return self.port_b_latch

    def write_port_c(self, value: int) -> None:
        self.port_c_latch = value & 0xFF
        self.machine._apply_psg_bus_control()
        self.machine._apply_tape_port_c()

    def read_port_c(self) -> int:
        return self.port_c_latch

    def write_control(self, value: int) -> None:
        value &= 0xFF
        if value & 0x80:
            self.control = value
            self.last_control_write = value
            self.port_a_input = bool(value & 0x10)
            self.port_b_input = bool(value & 0x02)
            self.port_c_upper_input = bool(value & 0x08)
            self.port_c_lower_input = bool(value & 0x01)
            return

        bit_index = (value >> 1) & 0x07
        if value & 0x01:
            self.port_c_latch |= 1 << bit_index
        else:
            self.port_c_latch &= ~(1 << bit_index)
        self.machine._apply_psg_bus_control()
        self.machine._apply_tape_port_c()
