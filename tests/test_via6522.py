from __future__ import annotations

from chipsets.via6522 import VIA6522


def test_via6522_port_reads_respect_ddr_masks():
    via = VIA6522()
    via.write(0x02, 0x0F)
    via.write(0x03, 0xF0)
    via.write(0x00, 0xA5)
    via.write(0x01, 0x5A)
    via.set_port_b_input(0x3C)
    via.set_port_a_input(0xC3)

    assert via.read(0x00) == 0x35
    assert via.read(0x01) == 0x53


def test_via6522_timer1_sets_ifr_and_irq_when_enabled():
    events: list[str] = []
    via = VIA6522()
    via.connect_irq(lambda: events.append("raise"), lambda: events.append("clear"))

    via.write(0x0E, 0xC0)  # enable T1 interrupt
    via.write(0x04, 0x02)
    via.write(0x05, 0x00)
    via.run_cycles(3)

    assert (via.read(0x0D) & 0x40) != 0
    assert (via.read(0x0D) & 0x80) != 0
    assert "raise" in events

    via.read(0x04)
    assert (via.read(0x0D) & 0x40) == 0


def test_via6522_timer1_one_shot_drives_pb7_high_on_underflow():
    via = VIA6522()
    via.write(0x02, 0x80)
    via.write(0x0B, via.ACR_T1_PB7_ENABLE)
    via.write(0x00, 0x00)
    via.write(0x04, 0x02)
    via.write(0x05, 0x00)

    assert (via.read(0x00) & 0x80) == 0x00
    via.run_cycles(3)
    assert (via.read(0x00) & 0x80) == 0x80


def test_via6522_timer1_one_shot_reloads_latch_after_showing_ffff():
    via = VIA6522()
    via.write(0x04, 0x02)
    via.write(0x05, 0x00)

    via.run_cycles(3)
    assert via.t1_counter == 0xFFFF
    assert via.t1_reload_delay is True
    assert via.t1_running is True

    via.run_cycles(1)
    assert via.t1_counter == 0x0002
    assert via.t1_reload_delay is False
    assert via.t1_running is False


def test_via6522_timer1_free_run_toggles_pb7_on_each_underflow():
    via = VIA6522()
    via.write(0x02, 0x80)
    via.write(0x0B, via.ACR_T1_PB7_ENABLE | via.ACR_T1_FREE_RUN)
    via.write(0x00, 0x00)
    via.write(0x04, 0x00)
    via.write(0x05, 0x00)

    assert (via.read(0x00) & 0x80) == 0x00
    via.run_cycles(1)
    assert (via.read(0x00) & 0x80) == 0x80
    via.run_cycles(2)
    assert (via.read(0x00) & 0x80) == 0x00


def test_via6522_timer1_free_run_handles_multiple_underflows_in_one_burst():
    via = VIA6522()
    via.write(0x02, 0x80)
    via.write(0x0B, via.ACR_T1_PB7_ENABLE | via.ACR_T1_FREE_RUN)
    via.write(0x00, 0x00)
    via.write(0x04, 0x00)
    via.write(0x05, 0x00)

    via.run_cycles(3)

    assert (via.read(0x00) & 0x80) == 0x00
    assert via.t1_counter == 0xFFFF
    assert via.t1_reload_delay is True


def test_via6522_timer2_sets_ifr_and_can_be_cleared_by_reading_counter_low():
    via = VIA6522()
    via.write(0x08, 0x01)
    via.write(0x09, 0x00)
    via.run_cycles(2)

    assert (via.read(0x0D) & 0x20) != 0

    via.read(0x08)
    assert (via.read(0x0D) & 0x20) == 0


def test_via6522_timer2_continues_from_ffff_after_underflow():
    via = VIA6522()
    via.write(0x08, 0x01)
    via.write(0x09, 0x00)

    via.run_cycles(2)
    assert via.t2_counter == 0xFFFF
    assert via.t2_running is True
    assert via.t2_post_underflow is True

    via.run_cycles(1)
    assert via.t2_counter == 0xFFFF
    via.run_cycles(1)
    assert via.t2_counter == 0xFFFE


def test_via6522_ier_write_uses_bit7_as_set_clear_control():
    via = VIA6522()

    via.write(0x0E, 0xC0)
    assert (via.read(0x0E) & 0x40) != 0

    via.write(0x0E, 0x40)
    assert (via.read(0x0E) & 0x40) == 0


def test_via6522_ifr_write_clears_requested_bits():
    via = VIA6522()
    via.write(0x08, 0x01)
    via.write(0x09, 0x00)
    via.run_cycles(2)

    via.write(0x0D, 0x20)

    assert (via.read(0x0D) & 0x20) == 0


def test_via6522_reading_ports_clears_line_interrupt_flags():
    via = VIA6522()
    via._set_ifr_bits(via.IFR_CA1 | via.IFR_CA2 | via.IFR_CB1 | via.IFR_CB2)

    via.read(0x00)
    assert (via.read(0x0D) & (via.IFR_CB1 | via.IFR_CB2)) == 0
    assert (via.read(0x0D) & (via.IFR_CA1 | via.IFR_CA2)) != 0

    via.read(0x01)
    assert (via.read(0x0D) & (via.IFR_CA1 | via.IFR_CA2)) == 0


def test_via6522_writing_ports_clears_line_interrupt_flags():
    via = VIA6522()
    via._set_ifr_bits(via.IFR_CA1 | via.IFR_CA2 | via.IFR_CB1 | via.IFR_CB2)

    via.write(0x00, 0x12)
    assert (via.read(0x0D) & (via.IFR_CB1 | via.IFR_CB2)) == 0
    assert (via.read(0x0D) & (via.IFR_CA1 | via.IFR_CA2)) != 0

    via.write(0x01, 0x34)
    assert (via.read(0x0D) & (via.IFR_CA1 | via.IFR_CA2)) == 0


def test_via6522_ca1_and_cb1_follow_pcr_edge_selection():
    via = VIA6522()

    via.write(0x0C, 0x00)
    via.signal_ca1(False)
    assert (via.read(0x0D) & via.IFR_CA1) != 0
    via.write(0x0D, via.IFR_CA1)
    via.signal_cb1(False)
    assert (via.read(0x0D) & via.IFR_CB1) != 0

    via.write(0x0C, via.PCR_CA1_POS_ACTIVE_EDGE | via.PCR_CB1_POS_ACTIVE_EDGE)
    via.signal_ca1(True)
    assert (via.read(0x0D) & via.IFR_CA1) != 0
    via.write(0x0D, via.IFR_CA1)
    via.signal_cb1(True)
    assert (via.read(0x0D) & via.IFR_CB1) != 0


def test_via6522_ca2_and_cb2_input_interrupts_follow_pcr_edge_selection():
    via = VIA6522()

    via.write(0x0C, 0x00)
    via.signal_ca2(False)
    via.signal_cb2(False)
    assert (via.read(0x0D) & via.IFR_CA2) != 0
    assert (via.read(0x0D) & via.IFR_CB2) != 0

    via.write(0x0D, via.IFR_CA2 | via.IFR_CB2)
    via.write(0x0C, via.PCR_CA2_INPUT_POS_ACTIVE_EDGE | via.PCR_CB2_INPUT_POS_ACTIVE_EDGE)
    via.signal_ca2(True)
    via.signal_cb2(True)
    assert (via.read(0x0D) & via.IFR_CA2) != 0
    assert (via.read(0x0D) & via.IFR_CB2) != 0


def test_via6522_pcr_static_output_modes_drive_ca2_and_cb2_states():
    via = VIA6522()

    via.write(0x0C, via.PCR_CA2_LOW_OUTPUT | via.PCR_CB2_LOW_OUTPUT)
    assert via.ca2_state == 0
    assert via.cb2_state == 0

    via.write(0x0C, via.PCR_CA2_HIGH_OUTPUT | via.PCR_CB2_HIGH_OUTPUT)
    assert via.ca2_state == 1
    assert via.cb2_state == 1


def test_via6522_ca2_and_cb2_independent_interrupts_survive_port_access():
    via = VIA6522()
    via.write(0x0C, via.PCR_CA2_INDEPENDENT_INTERRUPT | via.PCR_CB2_INDEPENDENT_INTERRUPT)
    via._set_ifr_bits(via.IFR_CA2 | via.IFR_CB2)

    via.read(0x00)
    via.read(0x01)

    assert (via.read(0x0D) & via.IFR_CA2) != 0
    assert (via.read(0x0D) & via.IFR_CB2) != 0


def test_via6522_port_a_and_b_input_latches_capture_values_on_control_edges():
    via = VIA6522()
    via.write(0x03, 0x00)
    via.write(0x02, 0x00)
    via.write(0x0B, via.ACR_PA_LATCH | via.ACR_PB_LATCH)

    via.set_port_a_input(0x12)
    via.set_port_b_input(0x34)
    via.signal_ca1(False)
    via.signal_cb1(False)

    via.set_port_a_input(0xAB)
    via.set_port_b_input(0xCD)

    assert via.read(0x01) == 0x12
    assert via.read(0x00) == 0x34


def test_via6522_enabling_port_latches_captures_current_input_if_flag_is_already_set():
    via = VIA6522()
    via.write(0x03, 0x00)
    via.write(0x02, 0x00)
    via.set_port_a_input(0x56)
    via.set_port_b_input(0x78)
    via._set_ifr_bits(via.IFR_CA1 | via.IFR_CB1)

    via.write(0x0B, via.ACR_PA_LATCH | via.ACR_PB_LATCH)

    via.set_port_a_input(0xAA)
    via.set_port_b_input(0xCC)

    assert via.read(0x01) == 0x56
    assert via.read(0x00) == 0x78


def test_via6522_shift_register_shifts_in_bits_on_cb1_rising_edges():
    via = VIA6522()
    via.write(0x0B, via.ACR_SR_IN_CB1)
    via.write(0x0A, 0x00)

    for bit in [1, 0, 1, 1, 0, 0, 1, 0]:
        via.signal_cb2(bool(bit))
        via.signal_cb1(False)
        via.signal_cb1(True)

    assert via.sr == 0xB2
    assert (via.read(0x0D) & via.IFR_SR) != 0


def test_via6522_shift_register_shifts_out_bits_on_cb1_falling_edges():
    via = VIA6522()
    via.write(0x0B, via.ACR_SR_OUT_CB1)
    via.write(0x0A, 0xA5)

    output_bits = [via.cb2_state]
    for _ in range(8):
        via.signal_cb1(False)
        output_bits.append(via.cb2_state)
        via.signal_cb1(True)

    assert output_bits[:8] == [1, 0, 1, 0, 0, 1, 0, 1]
    assert (via.read(0x0D) & via.IFR_SR) != 0


def test_via6522_shift_register_supports_phi2_input_mode():
    via = VIA6522()
    via.write(0x0B, via.ACR_SR_IN_PHI2)
    via.write(0x0A, 0x00)
    via.signal_cb2(True)
    via.run_cycles(16)

    assert via.sr == 0xFF
    assert (via.read(0x0D) & via.IFR_SR) != 0


def test_via6522_internal_sr_clock_modes_take_ownership_of_cb1():
    via = VIA6522()
    via.write(0x0B, via.ACR_SR_IN_PHI2)
    via.write(0x0A, 0x00)

    via.signal_cb1(False)

    assert via.cb1_state == 1
    assert (via.read(0x0D) & via.IFR_CB1) == 0


def test_via6522_sr_output_modes_take_ownership_of_cb2():
    via = VIA6522()
    via.write(0x0B, via.ACR_SR_OUT_T2)
    via.write(0x0A, 0x80)

    via.signal_cb2(False)

    assert via.cb2_state == 1
    assert (via.read(0x0D) & via.IFR_CB2) == 0


def test_via6522_reading_or_writing_sr_clears_sr_flag_and_restarts_shift():
    via = VIA6522()
    via.write(0x0B, via.ACR_SR_IN_PHI2)
    via.signal_cb2(True)
    via.write(0x0A, 0x00)
    via.run_cycles(16)
    assert (via.read(0x0D) & via.IFR_SR) != 0


def test_via6522_shift_register_supports_t2_input_mode():
    via = VIA6522()
    via.write(0x0B, via.ACR_SR_IN_T2)
    via.write(0x0A, 0x00)
    via.signal_cb2(True)
    via.write(0x08, 0x00)
    via.write(0x09, 0x00)

    for _ in range(32):
        via.run_cycles(1)

    assert via.sr == 0xFF
    assert (via.read(0x0D) & via.IFR_SR) != 0


def test_via6522_shift_register_supports_t2_output_mode():
    via = VIA6522()
    via.write(0x0B, via.ACR_SR_OUT_T2)
    via.write(0x0A, 0xA5)
    via.write(0x08, 0x00)
    via.write(0x09, 0x00)

    output_bits = [via.cb2_state]
    cb1_states = [via.cb1_state]
    for _ in range(32):
        via.run_cycles(1)
        output_bits.append(via.cb2_state)
        cb1_states.append(via.cb1_state)

    assert output_bits[::4][:8] == [1, 0, 1, 0, 0, 1, 0, 1]
    assert cb1_states[:8] == [1, 1, 0, 0, 1, 1, 0, 0]
    assert (via.read(0x0D) & via.IFR_SR) != 0


def test_via6522_shift_register_free_running_t2_output_repeats():
    via = VIA6522()
    via.write(0x0B, via.ACR_SR_OUT_FREE_T2)
    via.write(0x0A, 0xA6)
    via.write(0x08, 0x00)
    via.write(0x09, 0x00)

    seen = []
    for _ in range(66):
        seen.append(via.cb2_state)
        via.run_cycles(1)

    assert seen[::4][:8] == [1, 0, 1, 0, 0, 1, 1, 0]
    assert seen[32::4][:8] == seen[::4][:8]
    assert (via.read(0x0D) & via.IFR_SR) == 0


def test_via6522_phi2_output_mode_pulses_cb1_and_needs_16_cycles_per_byte():
    via = VIA6522()
    via.write(0x0B, via.ACR_SR_OUT_PHI2)
    via.write(0x0A, 0x80)

    cb1_states = [via.cb1_state]
    for _ in range(4):
        via.run_cycles(1)
        cb1_states.append(via.cb1_state)

    assert cb1_states == [1, 0, 1, 0, 1]
    assert (via.read(0x0D) & via.IFR_SR) == 0

    via.run_cycles(12)
    assert (via.read(0x0D) & via.IFR_SR) != 0


def test_via6522_handshake_output_drops_line_until_matching_control_edge():
    via = VIA6522()
    via.write(0x0C, 0x88)  # CA2 handshake output + CB2 handshake output

    via.write(0x01, 0x55)
    via.write(0x00, 0xAA)
    assert via.ca2_state == 0
    assert via.cb2_state == 0

    via.signal_ca1(False)
    via.signal_cb1(False)
    assert via.ca2_state == 1
    assert via.cb2_state == 1


def test_via6522_pulse_output_returns_line_high_immediately_after_access():
    via = VIA6522()
    via.write(0x0C, 0xAA)  # CA2 pulse output + CB2 pulse output

    via.write(0x01, 0x55)
    via.write(0x00, 0xAA)

    assert via.ca2_state == 1
    assert via.cb2_state == 1


def test_via6522_pra_nhs_avoids_port_a_handshake_side_effects():
    via = VIA6522()
    via.write(0x0C, via.PCR_CA2_HANDSHAKE_OUTPUT)
    via._set_ifr_bits(via.IFR_CA1 | via.IFR_CA2)

    via.read(0x0F)
    assert via.ca2_state == 1
    assert (via.read(0x0D) & (via.IFR_CA1 | via.IFR_CA2)) == (via.IFR_CA1 | via.IFR_CA2)

    via.read(0x01)
    assert via.ca2_state == 0
    assert (via.read(0x0D) & (via.IFR_CA1 | via.IFR_CA2)) == 0


def test_via6522_pra_nhs_write_avoids_port_a_handshake_side_effects():
    via = VIA6522()
    via.write(0x0C, via.PCR_CA2_HANDSHAKE_OUTPUT)
    via._set_ifr_bits(via.IFR_CA1 | via.IFR_CA2)

    via.write(0x0F, 0x55)
    assert via.ca2_state == 1
    assert (via.read(0x0D) & (via.IFR_CA1 | via.IFR_CA2)) == (via.IFR_CA1 | via.IFR_CA2)

    via.write(0x01, 0xAA)
    assert via.ca2_state == 0
    assert (via.read(0x0D) & (via.IFR_CA1 | via.IFR_CA2)) == 0
