from __future__ import annotations


class M6530:
    """Minimal 6530 RIOT model for the KIM-1 monitor."""

    size = 8
    DISPLAY_SCAN_CODES = {
        0x09: 0,
        0x0B: 1,
        0x0D: 2,
        0x0F: 3,
        0x11: 4,
        0x13: 5,
    }
    KEYPAD_SCAN_CODES = {
        0x01: 0,
        0x03: 1,
        0x05: 2,
        0x21: 0,
        0x23: 1,
        0x25: 2,
    }

    def __init__(self):
        self.irq_callback = None
        self.irq_clear_callback = None
        self.reset()

    def reset(self) -> None:
        self.port_a = 0x00
        self.port_b = 0x00
        self.ddr_a = 0x00
        self.ddr_b = 0x00
        self.port_a_input = 0x81
        self.port_b_input = 0xFF
        self.keyboard_mode = True
        self.timer = 0xFF
        self.timer_divider = 1
        self.timer_elapsed = 0
        self.timer_timeout = False
        self.display_digits = [0x00] * 6
        self.active_digit = None
        self.active_key_row = None
        self.key_rows = [0xFF] * 3
        self.clock = 0
        self.tty_bit_cycles = 500
        self.tty_calibration_scale = 4
        self._tty_rx_idle_high = True
        self._tty_rx_line_high = True
        self._tty_rx_schedule: list[tuple[int, bool]] = []
        self._tty_rx_next_cycle = 0
        self._tty_tx_edges: list[tuple[int, int]] = [(0, 1)]
        self._tty_tx_last_level = 1
        self._clear_irq_line()

    def run_cycles(self, cycles: int) -> None:
        if cycles <= 0:
            return
        self.clock += cycles
        self._advance_tty_rx()
        self.timer_elapsed += cycles
        while self.timer_elapsed >= self.timer_divider:
            self.timer_elapsed -= self.timer_divider
            if self.timer > 0:
                self.timer = (self.timer - 1) & 0xFF
            else:
                self.timer_timeout = True
                self._raise_irq()
                break

    def connect_irq(self, raise_callback, clear_callback=None) -> None:
        self.irq_callback = raise_callback
        self.irq_clear_callback = clear_callback

    def set_keypad_matrix(self, rows: list[int]) -> None:
        self.key_rows = [(row & 0xFF) for row in rows[:3]]
        while len(self.key_rows) < 3:
            self.key_rows.append(0xFF)

    def set_port_a_input(self, value: int) -> None:
        self.port_a_input = value & 0xFF

    def set_port_b_input(self, value: int) -> None:
        self.port_b_input = value & 0xFF

    def set_keyboard_mode(self, enabled: bool) -> None:
        self.keyboard_mode = bool(enabled)
        if enabled:
            self.port_a_input |= 0x01
        else:
            self.port_a_input &= 0xFE

    def set_serial_input(self, high: bool) -> None:
        self._tty_rx_idle_high = bool(high)
        if not self._tty_rx_schedule:
            self._tty_rx_line_high = self._tty_rx_idle_high

    def queue_tty_input(self, data: bytes, *, calibration: bool = False, bit_cycles: int | None = None) -> None:
        if bit_cycles is None:
            bit_cycles = self.tty_bit_cycles
            if calibration:
                bit_cycles = max(1, bit_cycles // self.tty_calibration_scale)
        start = max(self.clock + (bit_cycles * 2), self._tty_rx_next_cycle)
        last_level = self._tty_rx_schedule[-1][1] if self._tty_rx_schedule else self._tty_rx_line_high
        for byte in data:
            bits = [0]
            bits.extend((byte >> index) & 0x01 for index in range(8))
            bits.append(1)
            current = start
            for bit in bits:
                level = bool(bit)
                if level != last_level:
                    self._tty_rx_schedule.append((current, level))
                    last_level = level
                current += bit_cycles
            start = current + bit_cycles
        if last_level != self._tty_rx_idle_high:
            self._tty_rx_schedule.append((start, self._tty_rx_idle_high))
        self._tty_rx_next_cycle = start

    def queue_tty_calibration(self, data: bytes = b"X") -> None:
        self.queue_tty_input(data, calibration=True)

    def drain_tty_output(self) -> bytes:
        data = self._decode_tty_output()
        self._tty_tx_edges = [(self.clock, self._tty_tx_last_level)]
        return data

    def drain_tty_output_ascii(self) -> bytes:
        data = self.drain_tty_output()
        return bytes((byte & 0x7F) for byte in data if byte in (0x0D, 0x0A) or (byte & 0x7F) >= 0x20)

    def read(self, addr: int) -> int:
        addr &= 0x07
        if addr == 0x00:
            input_value = self._read_port_a_input()
            return (self.port_a & self.ddr_a) | (input_value & (~self.ddr_a & 0xFF))
        if addr == 0x01:
            return self.ddr_a
        if addr == 0x02:
            return (self.port_b & self.ddr_b) | (self.port_b_input & (~self.ddr_b & 0xFF))
        if addr == 0x03:
            return self.ddr_b
        if addr == 0x04:
            return self._read_timer_timeout_bit()
        if addr == 0x05:
            return self._read_timer_timeout_bit()
        if addr == 0x06:
            self.timer_timeout = False
            self._clear_irq_line()
            return self.timer
        if addr == 0x07:
            return self._read_timer_timeout_bit()
        return 0xFF

    def write(self, addr: int, value: int) -> None:
        addr &= 0x07
        value &= 0xFF
        if addr == 0x00:
            self.port_a = value
            self._latch_display_state()
            return
        if addr == 0x01:
            self.ddr_a = value
            self._latch_display_state()
            return
        if addr == 0x02:
            self.port_b = value
            self._capture_tty_output_bit(value)
            self._latch_display_state()
            return
        if addr == 0x03:
            self.ddr_b = value
            self._latch_display_state()
            return
        if addr == 0x04:
            self._start_timer(value, divider=1)
            return
        if addr == 0x05:
            self._start_timer(value, divider=8)
            return
        if addr == 0x06:
            self._start_timer(value, divider=64)
            return
        if addr == 0x07:
            self._start_timer(value, divider=1024)

    def _start_timer(self, value: int, *, divider: int) -> None:
        self.timer = value & 0xFF
        self.timer_divider = divider
        self.timer_elapsed = 0
        self.timer_timeout = False
        self._clear_irq_line()

    def _read_timer_timeout_bit(self) -> int:
        return 0x80 if self.timer_timeout else 0x00

    def _raise_irq(self) -> None:
        if self.irq_callback is not None:
            self.irq_callback()

    def _clear_irq_line(self) -> None:
        if self.irq_clear_callback is not None:
            self.irq_clear_callback()

    def _read_port_a_input(self) -> int:
        self._advance_tty_rx()
        serial_mask = 0x80 if self._tty_rx_line_high else 0x00
        base_input = (self.port_a_input & 0x01) | serial_mask
        if not self.keyboard_mode:
            return base_input
        if self.active_key_row is None:
            return base_input
        if self.active_key_row < len(self.key_rows):
            keypad_bits = self.key_rows[self.active_key_row] & 0x7F
            return serial_mask | keypad_bits
        return base_input

    def _advance_tty_rx(self) -> None:
        while self._tty_rx_schedule and self._tty_rx_schedule[0][0] <= self.clock:
            _, level = self._tty_rx_schedule.pop(0)
            self._tty_rx_line_high = level
        if not self._tty_rx_schedule:
            self._tty_rx_line_high = self._tty_rx_idle_high

    def _capture_tty_output_bit(self, value: int) -> None:
        level = value & 0x01
        if level != self._tty_tx_last_level:
            self._tty_tx_edges.append((self.clock, level))
            self._tty_tx_last_level = level

    def _tty_level_at(self, cycle: int) -> int:
        level = self._tty_tx_edges[0][1]
        for edge_cycle, edge_level in self._tty_tx_edges[1:]:
            if edge_cycle > cycle:
                break
            level = edge_level
        return level

    def _decode_tty_output(self) -> bytes:
        if len(self._tty_tx_edges) < 2:
            return b""
        out = bytearray()
        if len(self._tty_tx_edges) >= 5:
            deltas = [
                self._tty_tx_edges[index][0] - self._tty_tx_edges[index - 1][0]
                for index in range(1, len(self._tty_tx_edges))
                if self._tty_tx_edges[index][0] > self._tty_tx_edges[index - 1][0]
            ]
            if deltas:
                bit_cycles = min(deltas)
            else:
                bit_cycles = self.tty_bit_cycles
        else:
            bit_cycles = self.tty_bit_cycles
        index = 1
        while index < len(self._tty_tx_edges):
            start_cycle, level = self._tty_tx_edges[index]
            prev_level = self._tty_tx_edges[index - 1][1]
            if prev_level != 1 or level != 0:
                index += 1
                continue
            stop_sample = start_cycle + (bit_cycles * 19) // 2
            if stop_sample > self.clock:
                break
            value = 0
            for bit_index in range(8):
                sample_cycle = start_cycle + (bit_cycles * (3 + bit_index * 2)) // 2
                bit = self._tty_level_at(sample_cycle)
                value |= bit << bit_index
            if self._tty_level_at(stop_sample) == 1:
                out.append(value & 0xFF)
                while index < len(self._tty_tx_edges) and self._tty_tx_edges[index][0] <= stop_sample:
                    index += 1
                continue
            index += 1
        return bytes(out)

    def _latch_display_state(self) -> None:
        scan_code = self.port_b & 0x3F
        self.active_digit = self.DISPLAY_SCAN_CODES.get(scan_code)
        self.active_key_row = self.KEYPAD_SCAN_CODES.get(scan_code)

        segments = self.port_a & self.ddr_a
        if self.active_digit is not None and segments != 0:
            self.display_digits[self.active_digit] = segments & 0x7F
