from __future__ import annotations


class VIA6522:
    """Python reference 6522 VIA model.

    Keep this fallback aligned with the canonical Cython implementation in
    ``chipsets/via6522.pyx``.
    """

    size = 0x10

    IFR_CA2 = 0x01
    IFR_CA1 = 0x02
    IFR_SR = 0x04
    IFR_CB2 = 0x08
    IFR_CB1 = 0x10
    IFR_T2 = 0x20
    IFR_T1 = 0x40
    IFR_IRQ = 0x80

    PCR_CA1_POS_ACTIVE_EDGE = 0x01
    PCR_CA2_CONTROL = 0x0E
    PCR_CA2_INPUT = 0x00
    PCR_CA2_INPUT_POS_ACTIVE_EDGE = 0x04
    PCR_CA2_INDEPENDENT_INTERRUPT = 0x02
    PCR_CA2_HANDSHAKE_OUTPUT = 0x08
    PCR_CA2_PULSE_OUTPUT = 0x0A
    PCR_CA2_LOW_OUTPUT = 0x0C
    PCR_CA2_HIGH_OUTPUT = 0x0E
    PCR_CB1_POS_ACTIVE_EDGE = 0x10
    PCR_CB2_CONTROL = 0xE0
    PCR_CB2_INPUT = 0x00
    PCR_CB2_INPUT_POS_ACTIVE_EDGE = 0x40
    PCR_CB2_INDEPENDENT_INTERRUPT = 0x20
    PCR_CB2_HANDSHAKE_OUTPUT = 0x80
    PCR_CB2_PULSE_OUTPUT = 0xA0
    PCR_CB2_LOW_OUTPUT = 0xC0
    PCR_CB2_HIGH_OUTPUT = 0xE0
    ACR_PB_LATCH = 0x02
    ACR_PA_LATCH = 0x01
    ACR_T1_FREE_RUN = 0x40
    ACR_T1_PB7_ENABLE = 0x80
    ACR_SR_CONTROL = 0x1C
    ACR_SR_DISABLED = 0x00
    ACR_SR_IN_T2 = 0x04
    ACR_SR_IN_PHI2 = 0x08
    ACR_SR_IN_CB1 = 0x0C
    ACR_SR_OUT_FREE_T2 = 0x10
    ACR_SR_OUT_T2 = 0x14
    ACR_SR_OUT_PHI2 = 0x18
    ACR_SR_OUT_CB1 = 0x1C

    def __init__(self):
        self.irq_callback = None
        self.irq_clear_callback = None
        self.port_a_input_callback = None
        self.port_b_input_callback = None
        self.reset()

    def reset(self) -> None:
        self.orb = 0x00
        self.ora = 0x00
        self.ddrb = 0x00
        self.ddra = 0x00
        self.port_b_input = 0xFF
        self.port_a_input = 0xFF
        self.sr = 0x00
        self.acr = 0x00
        self.pcr = 0x00
        self.ifr = 0x00
        self.ier = 0x00
        self.t1_counter = 0
        self.t1_latch = 0
        self.t1_running = False
        self.t1_has_fired = False
        self.t1_reload_delay = False
        self.pb7_state = 0
        self.t2_counter = 0
        self.t2_latch = 0
        self.t2_running = False
        self.t2_has_fired = False
        self.t2_post_underflow = False
        self._t2_sr_shift_delay = 0
        self.ila = 0xFF
        self.ilb = 0xFF
        self.ca1_state = 1
        self.ca2_state = 1
        self.cb1_state = 1
        self.cb2_state = 1
        self._sr_active = False
        self._sr_shift_counter = 0
        self._sr_phase = 0
        self._sr_latch = 0x00
        self._update_irq_line()

    def connect_irq(self, raise_callback, clear_callback=None) -> None:
        self.irq_callback = raise_callback
        self.irq_clear_callback = clear_callback
        self._update_irq_line()

    def set_port_a_input(self, value: int) -> None:
        self.port_a_input = value & 0xFF

    def set_port_b_input(self, value: int) -> None:
        self.port_b_input = value & 0xFF

    def set_port_a_input_callback(self, callback) -> None:
        self.port_a_input_callback = callback

    def set_port_b_input_callback(self, callback) -> None:
        self.port_b_input_callback = callback

    def run_cycles(self, cycles: int) -> None:
        if cycles <= 0:
            return
        self._run_t1(cycles)
        self._run_t2(cycles)
        self._run_shift_register(cycles)

    def read(self, addr: int) -> int:
        reg = addr & 0x0F
        if reg == 0x00:
            port_b_input = self.ilb if (self.acr & self.ACR_PB_LATCH and (self.ifr & self.IFR_CB1)) else self._read_port_b_input()
            value = (self.orb & self.ddrb) | (port_b_input & (~self.ddrb & 0xFF))
            if self.acr & self.ACR_T1_PB7_ENABLE:
                value = (value & 0x7F) | ((self.pb7_state & 0x01) << 7)
            self._clear_port_b_ifr_bits()
            self._handle_cb2_output_after_access()
            return value
        if reg == 0x01:
            port_a_input = self.ila if (self.acr & self.ACR_PA_LATCH and (self.ifr & self.IFR_CA1)) else self._read_port_a_input()
            value = (self.ora & self.ddra) | (port_a_input & (~self.ddra & 0xFF))
            self._clear_port_a_ifr_bits()
            self._handle_ca2_output_after_access()
            return value
        if reg == 0x0F:
            port_a_input = self.ila if (self.acr & self.ACR_PA_LATCH and (self.ifr & self.IFR_CA1)) else self._read_port_a_input()
            return (self.ora & self.ddra) | (port_a_input & (~self.ddra & 0xFF))
        if reg == 0x02:
            return self.ddrb
        if reg == 0x03:
            return self.ddra
        if reg == 0x04:
            self._clear_ifr_bits(self.IFR_T1)
            return self.t1_counter & 0xFF
        if reg == 0x05:
            return (self.t1_counter >> 8) & 0xFF
        if reg == 0x06:
            return self.t1_latch & 0xFF
        if reg == 0x07:
            return (self.t1_latch >> 8) & 0xFF
        if reg == 0x08:
            self._clear_ifr_bits(self.IFR_T2)
            return self.t2_counter & 0xFF
        if reg == 0x09:
            return (self.t2_counter >> 8) & 0xFF
        if reg == 0x0A:
            self._clear_ifr_bits(self.IFR_SR)
            self._setup_shifting()
            return self.sr
        if reg == 0x0B:
            return self.acr
        if reg == 0x0C:
            return self.pcr
        if reg == 0x0D:
            return self._read_ifr()
        if reg == 0x0E:
            return self.ier | self.IFR_IRQ
        return 0xFF

    def write(self, addr: int, value: int) -> None:
        reg = addr & 0x0F
        value &= 0xFF
        if reg == 0x00:
            self.orb = value
            self._clear_port_b_ifr_bits()
            self._handle_cb2_output_after_access()
            return
        if reg == 0x01:
            self.ora = value
            self._clear_port_a_ifr_bits()
            self._handle_ca2_output_after_access()
            return
        if reg == 0x0F:
            self.ora = value
            return
        if reg == 0x02:
            self.ddrb = value
            return
        if reg == 0x03:
            self.ddra = value
            return
        if reg == 0x04:
            self.t1_latch = (self.t1_latch & 0xFF00) | value
            return
        if reg == 0x05:
            self.t1_latch = ((value << 8) | (self.t1_latch & 0x00FF)) & 0xFFFF
            self.t1_counter = self.t1_latch
            self.t1_running = True
            self.t1_has_fired = False
            self.t1_reload_delay = False
            if self.acr & self.ACR_T1_PB7_ENABLE:
                self.pb7_state = 0
            self._clear_ifr_bits(self.IFR_T1)
            return
        if reg == 0x06:
            self.t1_latch = (self.t1_latch & 0xFF00) | value
            return
        if reg == 0x07:
            self.t1_latch = ((value << 8) | (self.t1_latch & 0x00FF)) & 0xFFFF
            self._clear_ifr_bits(self.IFR_T1)
            return
        if reg == 0x08:
            self.t2_latch = (self.t2_latch & 0xFF00) | value
            return
        if reg == 0x09:
            self.t2_latch = ((value << 8) | (self.t2_latch & 0x00FF)) & 0xFFFF
            self.t2_counter = self.t2_latch
            self.t2_running = True
            self.t2_has_fired = False
            self.t2_post_underflow = False
            self._t2_sr_shift_delay = 0
            self._clear_ifr_bits(self.IFR_T2)
            return
        if reg == 0x0A:
            self.sr = value
            self._sr_latch = value
            self._clear_ifr_bits(self.IFR_SR)
            self._setup_shifting()
            return
        if reg == 0x0B:
            old_acr = self.acr
            self.acr = value
            if not (value & self.ACR_T1_PB7_ENABLE):
                self.pb7_state = 0
            if not (old_acr & self.ACR_PA_LATCH) and (value & self.ACR_PA_LATCH) and (self.ifr & self.IFR_CA1):
                self.ila = self._read_port_a_input()
            if not (old_acr & self.ACR_PB_LATCH) and (value & self.ACR_PB_LATCH) and (self.ifr & self.IFR_CB1):
                self.ilb = self._read_port_b_input()
            if (value & self.ACR_SR_CONTROL) == self.ACR_SR_DISABLED:
                self._sr_active = False
                self._sr_shift_counter = 0
                self._sr_phase = 0
                self._clear_ifr_bits(self.IFR_SR)
            else:
                self._setup_shifting()
            return
        if reg == 0x0C:
            self.pcr = value
            self._update_control_output_states()
            return
        if reg == 0x0D:
            self._clear_ifr_bits(value & 0x7F)
            return
        if reg == 0x0E:
            if value & self.IFR_IRQ:
                self.ier |= value & 0x7F
            else:
                self.ier &= ~(value & 0x7F)
            self._update_irq_line()

    def _run_t1(self, cycles: int) -> None:
        if not self.t1_running:
            return
        if self.acr & self.ACR_T1_FREE_RUN:
            remaining = cycles
            while remaining > 0:
                if self.t1_reload_delay:
                    self.t1_counter = self.t1_latch
                    self.t1_reload_delay = False
                    remaining -= 1
                    continue
                if remaining <= self.t1_counter:
                    self.t1_counter -= remaining
                    break
                remaining -= self.t1_counter + 1
                self._set_ifr_bits(self.IFR_T1)
                if self.acr & self.ACR_T1_PB7_ENABLE:
                    self.pb7_state ^= 0x01
                self.t1_counter = 0xFFFF
                self.t1_reload_delay = True
        else:
            remaining = cycles
            while remaining > 0 and self.t1_running:
                if self.t1_reload_delay:
                    self.t1_counter = self.t1_latch
                    self.t1_reload_delay = False
                    self.t1_running = False
                    remaining -= 1
                    continue
                if remaining <= self.t1_counter:
                    self.t1_counter -= remaining
                    break
                remaining -= self.t1_counter + 1
                if not self.t1_has_fired:
                    self._set_ifr_bits(self.IFR_T1)
                    self.t1_has_fired = True
                    if self.acr & self.ACR_T1_PB7_ENABLE:
                        self.pb7_state = 1
                self.t1_counter = 0xFFFF
                self.t1_reload_delay = True

    def _run_t2(self, cycles: int) -> None:
        if not self.t2_running:
            return
        remaining = cycles
        while self.t2_running and remaining > 0:
            if self.t2_post_underflow:
                self.t2_post_underflow = False
                mode = self.acr & self.ACR_SR_CONTROL
                if mode in {self.ACR_SR_IN_T2, self.ACR_SR_OUT_T2, self.ACR_SR_OUT_FREE_T2}:
                    self.t2_counter = self.t2_latch
                else:
                    self.t2_counter = 0xFFFF
                if self._t2_sr_shift_delay > 0:
                    self._t2_sr_shift_delay -= 1
                    if self._t2_sr_shift_delay == 0 and self._sr_active and mode in {
                        self.ACR_SR_IN_T2,
                        self.ACR_SR_OUT_T2,
                        self.ACR_SR_OUT_FREE_T2,
                    }:
                        self._advance_internal_shift_phase(
                            input_bit=self.cb2_state if mode == self.ACR_SR_IN_T2 else None
                        )
                remaining -= 1
                continue
            if remaining <= self.t2_counter:
                self.t2_counter -= remaining
                break
            remaining -= self.t2_counter + 1
            self._on_t2_underflow()

    def _read_ifr(self) -> int:
        if self.ifr & self.ier:
            return self.ifr | self.IFR_IRQ
        return self.ifr & 0x7F

    def _read_port_a_input(self) -> int:
        if self.port_a_input_callback is not None:
            return self.port_a_input_callback() & 0xFF
        return self.port_a_input

    def _read_port_b_input(self) -> int:
        if self.port_b_input_callback is not None:
            return self.port_b_input_callback() & 0xFF
        return self.port_b_input

    def _set_ifr_bits(self, mask: int) -> None:
        self.ifr |= mask & 0x7F
        self._update_irq_line()

    def _clear_ifr_bits(self, mask: int) -> None:
        self.ifr &= ~(mask & 0x7F)
        self._update_irq_line()

    def _clear_port_a_ifr_bits(self) -> None:
        mask = self.IFR_CA1
        if (self.pcr & self.PCR_CA2_INDEPENDENT_INTERRUPT) == 0:
            mask |= self.IFR_CA2
        self._clear_ifr_bits(mask)

    def _clear_port_b_ifr_bits(self) -> None:
        mask = self.IFR_CB1
        if (self.pcr & self.PCR_CB2_INDEPENDENT_INTERRUPT) == 0:
            mask |= self.IFR_CB2
        self._clear_ifr_bits(mask)

    def signal_ca1(self, state: bool) -> None:
        new_state = 1 if state else 0
        if new_state == self.ca1_state:
            return
        rising = self.ca1_state == 0 and new_state == 1
        self.ca1_state = new_state
        if rising == bool(self.pcr & self.PCR_CA1_POS_ACTIVE_EDGE):
            if self.acr & self.ACR_PA_LATCH:
                self.ila = self._read_port_a_input()
            if self._is_ca2_handshake_or_pulse_mode() and self.ca2_state == 0:
                self.ca2_state = 1
            self._set_ifr_bits(self.IFR_CA1)

    def signal_ca2(self, state: bool) -> None:
        new_state = 1 if state else 0
        if new_state == self.ca2_state:
            return
        old_state = self.ca2_state
        self.ca2_state = new_state
        if (self.pcr & 0x08) != self.PCR_CA2_INPUT:
            return
        rising = old_state == 0 and new_state == 1
        if rising == bool(self.pcr & self.PCR_CA2_INPUT_POS_ACTIVE_EDGE):
            self._set_ifr_bits(self.IFR_CA2)

    def signal_cb1(self, state: bool) -> None:
        if self._sr_controls_cb1():
            return
        new_state = 1 if state else 0
        if new_state == self.cb1_state:
            return
        old_state = self.cb1_state
        rising = self.cb1_state == 0 and new_state == 1
        self.cb1_state = new_state
        self._handle_cb1_serial_edge(old_state, new_state)
        if rising == bool(self.pcr & self.PCR_CB1_POS_ACTIVE_EDGE):
            if self.acr & self.ACR_PB_LATCH:
                self.ilb = self._read_port_b_input()
            if self._is_cb2_handshake_or_pulse_mode() and self.cb2_state == 0:
                self.cb2_state = 1
            self._set_ifr_bits(self.IFR_CB1)

    def signal_cb2(self, state: bool) -> None:
        if self._sr_controls_cb2():
            return
        new_state = 1 if state else 0
        if new_state == self.cb2_state:
            return
        old_state = self.cb2_state
        self.cb2_state = new_state
        if (self.pcr & 0x80) != self.PCR_CB2_INPUT:
            return
        rising = old_state == 0 and new_state == 1
        if rising == bool(self.pcr & self.PCR_CB2_INPUT_POS_ACTIVE_EDGE):
            self._set_ifr_bits(self.IFR_CB2)

    def _update_irq_line(self) -> None:
        active = (self.ifr & self.ier & 0x7F) != 0
        if active:
            if self.irq_callback is not None:
                self.irq_callback()
        else:
            if self.irq_clear_callback is not None:
                self.irq_clear_callback()

    def _update_control_output_states(self) -> None:
        ca2_mode = self.pcr & self.PCR_CA2_CONTROL
        if ca2_mode == self.PCR_CA2_LOW_OUTPUT:
            self.ca2_state = 0
        elif ca2_mode == self.PCR_CA2_HIGH_OUTPUT:
            self.ca2_state = 1
        elif (ca2_mode & 0x08) != 0:
            self.ca2_state = 1

        cb2_mode = self.pcr & self.PCR_CB2_CONTROL
        if cb2_mode == self.PCR_CB2_LOW_OUTPUT:
            self.cb2_state = 0
        elif cb2_mode == self.PCR_CB2_HIGH_OUTPUT:
            self.cb2_state = 1
        elif (cb2_mode & 0x80) != 0:
            self.cb2_state = 1

    def _is_ca2_handshake_or_pulse_mode(self) -> bool:
        mode = self.pcr & self.PCR_CA2_CONTROL
        return mode in {self.PCR_CA2_HANDSHAKE_OUTPUT, self.PCR_CA2_PULSE_OUTPUT}

    def _is_ca2_pulse_mode(self) -> bool:
        return (self.pcr & self.PCR_CA2_CONTROL) == self.PCR_CA2_PULSE_OUTPUT

    def _is_cb2_handshake_or_pulse_mode(self) -> bool:
        mode = self.pcr & self.PCR_CB2_CONTROL
        return mode in {self.PCR_CB2_HANDSHAKE_OUTPUT, self.PCR_CB2_PULSE_OUTPUT}

    def _is_cb2_pulse_mode(self) -> bool:
        return (self.pcr & self.PCR_CB2_CONTROL) == self.PCR_CB2_PULSE_OUTPUT

    def _handle_ca2_output_after_access(self) -> None:
        if not self._is_ca2_handshake_or_pulse_mode():
            return
        self.ca2_state = 0
        if self._is_ca2_pulse_mode():
            self.ca2_state = 1

    def _handle_cb2_output_after_access(self) -> None:
        if not self._is_cb2_handshake_or_pulse_mode():
            return
        self.cb2_state = 0
        if self._is_cb2_pulse_mode():
            self.cb2_state = 1

    def _setup_shifting(self) -> None:
        mode = self.acr & self.ACR_SR_CONTROL
        if mode == self.ACR_SR_DISABLED:
            return
        if not self._sr_active:
            self._sr_active = True
            self._sr_shift_counter = 0
            self._sr_phase = 0
        if self._sr_controls_cb1():
            self.cb1_state = 1
        if self._is_sr_output_mode():
            self.cb2_state = (self.sr >> 7) & 0x01

    def _is_sr_output_mode(self) -> bool:
        return (self.acr & self.ACR_SR_CONTROL) in {
            self.ACR_SR_OUT_FREE_T2,
            self.ACR_SR_OUT_T2,
            self.ACR_SR_OUT_PHI2,
            self.ACR_SR_OUT_CB1,
        }

    def _sr_controls_cb1(self) -> bool:
        return (self.acr & self.ACR_SR_CONTROL) in {
            self.ACR_SR_IN_T2,
            self.ACR_SR_IN_PHI2,
            self.ACR_SR_OUT_FREE_T2,
            self.ACR_SR_OUT_T2,
            self.ACR_SR_OUT_PHI2,
        }

    def _sr_controls_cb2(self) -> bool:
        return self._is_sr_output_mode()

    def _run_shift_register(self, cycles: int) -> None:
        mode = self.acr & self.ACR_SR_CONTROL
        if not self._sr_active:
            return
        if mode in {self.ACR_SR_IN_PHI2, self.ACR_SR_OUT_PHI2}:
            for _ in range(cycles):
                self._advance_internal_shift_phase(input_bit=self.cb2_state if mode == self.ACR_SR_IN_PHI2 else None)

    def _handle_cb1_serial_edge(self, old_state: int, new_state: int) -> None:
        if not self._sr_active:
            return
        mode = self.acr & self.ACR_SR_CONTROL
        if mode == self.ACR_SR_IN_CB1 and old_state == 0 and new_state == 1:
            self._shift_once(input_bit=self.cb2_state)
        elif mode == self.ACR_SR_OUT_CB1 and old_state == 1 and new_state == 0:
            self._shift_once(input_bit=None)

    def _advance_internal_shift_phase(self, *, input_bit: int | None) -> None:
        mode = self.acr & self.ACR_SR_CONTROL
        shift_out = self._is_sr_output_mode()
        if (self._sr_phase & 1) == 0:
            if self._sr_controls_cb1():
                self.cb1_state = 0
            if shift_out:
                self._shift_once(input_bit=None)
        else:
            if self._sr_controls_cb1():
                self.cb1_state = 1
            if not shift_out:
                self._shift_once(input_bit=input_bit)
        self._sr_phase = (self._sr_phase + 1) & 0x0F

    def _shift_once(self, *, input_bit: int | None) -> None:
        mode = self.acr & self.ACR_SR_CONTROL
        if self._is_sr_output_mode():
            output_bit = (self.sr >> 7) & 0x01
            self.sr = ((self.sr << 1) | output_bit) & 0xFF
            self._sr_shift_counter += 1
            if self._sr_shift_counter >= 8:
                if mode == self.ACR_SR_OUT_FREE_T2:
                    self._sr_shift_counter = 0
                    self._sr_phase = 0
                else:
                    self._set_ifr_bits(self.IFR_SR)
                    self._sr_active = False
                    if self._sr_controls_cb1():
                        self.cb1_state = 1
            if self._sr_active or mode == self.ACR_SR_OUT_FREE_T2:
                self.cb2_state = (self.sr >> 7) & 0x01
            return

        if input_bit is None:
            input_bit = self.cb2_state
        self.sr = ((self.sr << 1) | (input_bit & 0x01)) & 0xFF
        self._sr_shift_counter += 1
        if self._sr_shift_counter >= 8:
            self._set_ifr_bits(self.IFR_SR)
            self._sr_active = False
            self._sr_phase = 0
            if self._sr_controls_cb1():
                self.cb1_state = 1

    def _on_t2_underflow(self) -> None:
        if not self.t2_has_fired:
            self._set_ifr_bits(self.IFR_T2)
            self.t2_has_fired = True

        mode = self.acr & self.ACR_SR_CONTROL
        if mode == self.ACR_SR_OUT_FREE_T2 and self.t2_latch >= 0:
            self.t2_counter = 0xFFFF
            self.t2_running = True
            self.t2_has_fired = False
            self.t2_post_underflow = True
            self._t2_sr_shift_delay = 1
            return

        if self._sr_active and mode in {self.ACR_SR_IN_T2, self.ACR_SR_OUT_T2} and self.t2_latch >= 0:
            self.t2_counter = 0xFFFF
            self.t2_running = True
            self.t2_has_fired = False
            self.t2_post_underflow = True
            self._t2_sr_shift_delay = 1
            return

        self.t2_running = True
        self.t2_counter = 0xFFFF
        self.t2_post_underflow = True
