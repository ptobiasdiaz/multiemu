from __future__ import annotations

from pathlib import Path


OUT_PORT_A = 0xF400
OUT_PORT_C = 0xF600
OUT_CONTROL = 0xF700


class RomBuilder:
    def __init__(self) -> None:
        self.buf = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str, str]] = []

    @property
    def pc(self) -> int:
        return len(self.buf)

    def label(self, name: str) -> None:
        self.labels[name] = self.pc

    def emit(self, *values: int) -> None:
        self.buf.extend(value & 0xFF for value in values)

    def di(self) -> None:
        self.emit(0xF3)

    def ei(self) -> None:
        self.emit(0xFB)

    def ld_sp_nn(self, value: int) -> None:
        self.emit(0x31, value & 0xFF, (value >> 8) & 0xFF)

    def ld_bc_nn(self, value: int) -> None:
        self.emit(0x01, value & 0xFF, (value >> 8) & 0xFF)

    def ld_hl_nn(self, value: int) -> None:
        self.emit(0x21, value & 0xFF, (value >> 8) & 0xFF)

    def ld_a_n(self, value: int) -> None:
        self.emit(0x3E, value)

    def ld_b_n(self, value: int) -> None:
        self.emit(0x06, value)

    def ld_c_n(self, value: int) -> None:
        self.emit(0x0E, value)

    def ld_d_n(self, value: int) -> None:
        self.emit(0x16, value)

    def ld_a_hlp(self) -> None:
        self.emit(0x7E)

    def ld_d_a(self) -> None:
        self.emit(0x57)

    def ld_e_a(self) -> None:
        self.emit(0x5F)

    def ld_a_e(self) -> None:
        self.emit(0x7B)

    def ld_b_d(self) -> None:
        self.emit(0x42)

    def inc_hl(self) -> None:
        self.emit(0x23)

    def dec_c(self) -> None:
        self.emit(0x0D)

    def djnz(self, label: str) -> None:
        self.emit(0x10, 0x00)
        self.fixups.append((self.pc - 1, label, "rel8"))

    def jr_nz(self, label: str) -> None:
        self.emit(0x20, 0x00)
        self.fixups.append((self.pc - 1, label, "rel8"))

    def jp(self, label: str) -> None:
        self.emit(0xC3, 0x00, 0x00)
        self.fixups.append((self.pc - 2, label, "abs16"))

    def call(self, label: str) -> None:
        self.emit(0xCD, 0x00, 0x00)
        self.fixups.append((self.pc - 2, label, "abs16"))

    def ret(self) -> None:
        self.emit(0xC9)

    def halt(self) -> None:
        self.emit(0x76)

    def out_c_a(self, port: int) -> None:
        self.ld_bc_nn(port)
        self.emit(0xED, 0x79)

    def resolve(self) -> bytes:
        for pos, label, kind in self.fixups:
            target = self.labels[label]
            if kind == "abs16":
                self.buf[pos] = target & 0xFF
                self.buf[pos + 1] = (target >> 8) & 0xFF
                continue

            if kind == "rel8":
                base = pos + 1
                delta = target - base
                if not -128 <= delta <= 127:
                    raise ValueError(f"jump out of range for {label!r}: {delta}")
                self.buf[pos] = delta & 0xFF
                continue

            raise ValueError(f"unknown fixup kind: {kind}")

        if len(self.buf) > 0x4000:
            raise ValueError("ROM generated larger than 16 KiB")

        return bytes(self.buf) + bytes(0x4000 - len(self.buf))


def _emit_select_register(rom: RomBuilder, register_index: int) -> None:
    rom.ld_a_n(0x00)
    rom.out_c_a(OUT_PORT_C)
    rom.ld_a_n(register_index)
    rom.out_c_a(OUT_PORT_A)
    rom.ld_a_n(0xC0)
    rom.out_c_a(OUT_PORT_C)
    rom.ld_a_n(0x00)
    rom.out_c_a(OUT_PORT_C)


def _emit_write_selected(rom: RomBuilder, value: int) -> None:
    rom.ld_a_n(0x00)
    rom.out_c_a(OUT_PORT_C)
    rom.ld_a_n(value)
    rom.out_c_a(OUT_PORT_A)
    rom.ld_a_n(0x80)
    rom.out_c_a(OUT_PORT_C)
    rom.ld_a_n(0x00)
    rom.out_c_a(OUT_PORT_C)


def _emit_write_selected_from_a(rom: RomBuilder) -> None:
    rom.ld_a_n(0x00)
    rom.out_c_a(OUT_PORT_C)
    rom.ld_a_e()
    rom.out_c_a(OUT_PORT_A)
    rom.ld_a_n(0x80)
    rom.out_c_a(OUT_PORT_C)
    rom.ld_a_n(0x00)
    rom.out_c_a(OUT_PORT_C)


def build_rom() -> bytes:
    rom = RomBuilder()

    rom.di()
    rom.ld_sp_nn(0xBFFF)

    rom.ld_a_n(0x82)
    rom.out_c_a(OUT_CONTROL)

    _emit_select_register(rom, 7)
    _emit_write_selected(rom, 0xFE)
    _emit_select_register(rom, 8)
    _emit_write_selected(rom, 0x0F)
    _emit_select_register(rom, 9)
    _emit_write_selected(rom, 0x00)
    _emit_select_register(rom, 10)
    _emit_write_selected(rom, 0x00)
    _emit_select_register(rom, 1)
    _emit_write_selected(rom, 0x00)
    rom.ei()

    rom.label("main_loop")
    rom.ld_hl_nn(0x0000)
    rom.fixups.append((rom.pc - 2, "note_table", "abs16"))

    rom.label("next_note")
    rom.ld_a_hlp()
    rom.emit(0xFE, 0xFF)  # CP FFh
    rom.jr_nz("have_note")
    rom.jp("main_loop")
    rom.label("have_note")
    rom.inc_hl()
    rom.ld_e_a()
    rom.ld_a_hlp()
    rom.inc_hl()
    rom.ld_d_a()
    _emit_select_register(rom, 0)
    _emit_write_selected_from_a(rom)
    rom.ld_a_n(0x0F)
    rom.emit(0xBB)  # CP E
    rom.jr_nz("note_is_sound")
    rom.ld_a_n(0x00)
    rom.label("note_is_sound")
    rom.ld_e_a()
    _emit_select_register(rom, 8)
    _emit_write_selected_from_a(rom)

    rom.call("wait_frames")
    rom.jp("next_note")

    rom.label("wait_frames")
    rom.ld_b_d()
    rom.label("wait_frame_loop")
    rom.halt()
    rom.djnz("wait_frame_loop")
    rom.ret()

    rom.label("note_table")
    rom.emit(
        # Ode to Joy opening in C major, encoded as (period, duration).
        190, 10, 190, 10, 179, 10, 159, 10,
        159, 10, 179, 10, 190, 10, 213, 10,
        239, 10, 239, 10, 213, 10, 190, 10,
        190, 14, 213, 6, 213, 20,
        190, 10, 190, 10, 179, 10, 159, 10,
        159, 10, 179, 10, 190, 10, 213, 10,
        239, 10, 239, 10, 213, 10, 190, 10,
        213, 14, 239, 6, 239, 20,
        213, 10, 213, 10, 190, 10, 239, 10,
        213, 10, 190, 10, 179, 10, 190, 10,
        159, 10, 190, 10, 213, 10, 159, 10,
        190, 14, 213, 6, 159, 20,
        190, 10, 190, 10, 179, 10, 159, 10,
        159, 10, 179, 10, 190, 10, 213, 10,
        239, 10, 239, 10, 213, 10, 190, 10,
        213, 14, 239, 6, 239, 20,
        0, 12,
        0xFF,
    )

    return rom.resolve()


def main() -> None:
    output = Path("roms/generated/cpc_ode_to_joy.rom")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(build_rom())
    print(output)


if __name__ == "__main__":
    main()
