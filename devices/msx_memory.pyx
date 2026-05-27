# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False
# cython: cdivision=True

from cpu.z80.bus cimport MemoryDevice


cdef class MSXMemoryMap(MemoryDevice):
    cdef public object machine

    def __cinit__(self, object machine):
        self.machine = machine

    cpdef unsigned char read(self, unsigned short addr):
        cdef object m = self.machine
        cdef int page = (addr >> 14) & 0x03
        cdef int offset = addr & 0x3FFF
        cdef int slot = (m.slot_register >> (page * 2)) & 0x03

        if slot == 0:
            if addr == 0xFFFF:
                return <unsigned char>(m.subslot_register & 0xFF)
            subslot = (m.subslot_register >> (page * 2)) & 0x03
            if subslot == 1:
                return <unsigned char>self._read_cart_window(
                    m.cart1_data,
                    m.cart1_banks,
                    m.cart1_bank_registers,
                    m.cart1_mapper,
                    page,
                    offset,
                )
            if subslot == 2:
                return <unsigned char>self._read_cart_window(
                    m.cart2_data,
                    m.cart2_banks,
                    m.cart2_bank_registers,
                    m.cart2_mapper,
                    page,
                    offset,
                )
            if page == 0:
                return <unsigned char>m.bios_data[offset]
            if page == 1 and m.basic_blob:
                return <unsigned char>m.basic_data[offset]
            return 0xFF

        if slot == 1:
            return <unsigned char>self._read_cart_window(
                m.cart1_data,
                m.cart1_banks,
                m.cart1_bank_registers,
                m.cart1_mapper,
                page,
                offset,
            )

        if slot == 2:
            if not m.cart2_blob:
                return <unsigned char>m.ram[(page * m.PAGE_SIZE) + offset]
            if page == 1 or page == 2:
                return <unsigned char>self._read_cart_window(
                    m.cart2_data,
                    m.cart2_banks,
                    m.cart2_bank_registers,
                    m.cart2_mapper,
                    page,
                    offset,
                )
            return <unsigned char>m.ram[(page * m.PAGE_SIZE) + offset]

        if slot == 3:
            return <unsigned char>m.ram[(page * m.PAGE_SIZE) + offset]

        return 0xFF

    cpdef void write(self, unsigned short addr, unsigned char value):
        cdef object m = self.machine
        cdef int page = (addr >> 14) & 0x03
        cdef int offset = addr & 0x3FFF
        cdef int slot = (m.slot_register >> (page * 2)) & 0x03
        cdef int subslot

        if slot == 0:
            if addr == 0xFFFF:
                m.subslot_register = value & 0xFF
                return
            subslot = (m.subslot_register >> (page * 2)) & 0x03
            if subslot == 1 and self._write_cart_window(m, 1, addr, value):
                return
            if subslot == 2 and self._write_cart_window(m, 2, addr, value):
                return

        if slot == 1 and self._write_cart_window(m, 1, addr, value):
            return

        if slot == 2 and (page == 1 or page == 2) and self._write_cart_window(m, 2, addr, value):
            return

        if slot == 2 and not m.cart2_blob:
            m.ram[(page * m.PAGE_SIZE) + offset] = value & 0xFF
            return

        if slot == 2 or slot == 3:
            m.ram[(page * m.PAGE_SIZE) + offset] = value & 0xFF

    cpdef int peek(self, int addr):
        return self.read(<unsigned short>(addr & 0xFFFF))

    cpdef void poke(self, int addr, int value):
        self.write(<unsigned short>(addr & 0xFFFF), <unsigned char>(value & 0xFF))

    cdef int _read_16k_cart_bank(self, object cart_banks, int bank16, int offset):
        cdef int bank_pairs = max(1, len(cart_banks) // 2)
        cdef int bank = ((bank16 & 0xFF) % bank_pairs) * 2
        if offset >= 0x2000:
            bank += 1
        return cart_banks[bank % len(cart_banks)][offset & 0x1FFF]

    cdef int _read_cart_window(
        self,
        object cart_data,
        object cart_banks,
        object bank_registers,
        object mapper,
        int page,
        int offset,
    ):
        cdef int index
        cdef int bank
        cdef int segment
        cdef int bank_offset

        if mapper == "linear" or len(cart_banks) <= 4 or not cart_banks:
            if page != 1 and page != 2:
                return 0xFF
            index = ((page - 1) * 0x4000) + offset
            if 0 <= index < len(cart_data):
                return cart_data[index]
            return 0xFF

        if mapper == "konami":
            if page == 0:
                page = 1
            elif page == 3:
                page = 2
            elif page != 1 and page != 2:
                return 0xFF
            if page == 1 and offset < 0x2000:
                return cart_banks[0][offset]
            if page == 1:
                bank = bank_registers[1] % len(cart_banks)
                return cart_banks[bank][offset - 0x2000]
            if page == 2 and offset < 0x2000:
                bank = bank_registers[2] % len(cart_banks)
                return cart_banks[bank][offset]
            bank = bank_registers[3] % len(cart_banks)
            return cart_banks[bank][offset - 0x2000]

        if mapper == "konami_scc":
            if page == 0:
                page = 2
            elif page == 3:
                page = 1
            elif page != 1 and page != 2:
                return 0xFF
            segment = ((page - 1) * 2) + (1 if offset >= 0x2000 else 0)
            bank = bank_registers[segment] % len(cart_banks)
            bank_offset = offset & 0x1FFF
            return cart_banks[bank][bank_offset]

        if mapper == "ascii8" or mapper == "generic8" or mapper == "zemina8" or mapper == "holy_quran":
            if page != 1 and page != 2:
                return 0xFF
            segment = ((page - 1) * 2) + (1 if offset >= 0x2000 else 0)
            bank = bank_registers[segment] % len(cart_banks)
            bank_offset = offset & 0x1FFF
            return cart_banks[bank][bank_offset]

        if mapper == "cross_blaim":
            if page != 1 and page != 2:
                return 0xFF
            if page == 1:
                return self._read_16k_cart_bank(cart_banks, 0, offset)
            return self._read_16k_cart_bank(cart_banks, bank_registers[1], offset)

        if mapper == "rtype":
            if page != 1 and page != 2:
                return 0xFF
            if page == 1:
                return self._read_16k_cart_bank(cart_banks, 0x17, offset)
            return self._read_16k_cart_bank(cart_banks, bank_registers[1], offset)

        if mapper == "ascii16" or mapper == "generic16" or mapper == "zemina16" or mapper == "harry_fox":
            if page != 1 and page != 2:
                return 0xFF
            segment = 0 if page == 1 else 1
            return self._read_16k_cart_bank(cart_banks, bank_registers[segment], offset)

        if page != 1 and page != 2:
            return 0xFF
        segment = ((page - 1) * 2) + (1 if offset >= 0x2000 else 0)
        bank = bank_registers[segment] % len(cart_banks)
        bank_offset = offset & 0x1FFF
        return cart_banks[bank][bank_offset]

    cdef bint _write_cart_window(self, object m, int cart_index, int addr, int value):
        cdef object cart_banks
        cdef object bank_registers
        cdef object mapper
        cdef int segment

        if cart_index == 1:
            cart_banks = m.cart1_banks
            bank_registers = m.cart1_bank_registers
            mapper = m.cart1_mapper
        else:
            cart_banks = m.cart2_banks
            bank_registers = m.cart2_bank_registers
            mapper = m.cart2_mapper

        if len(cart_banks) <= 4:
            return False
        if addr < 0x4000 or addr > 0xBFFF:
            return False

        if mapper == "unknown":
            if 0x9000 <= addr <= 0x97FF:
                mapper = "konami_scc"
                self._set_cart_mapper(m, cart_index, mapper)
                bank_registers[:] = m._default_cart_bank_registers(mapper)
            elif 0x6800 <= addr <= 0x6FFF or 0x7800 <= addr <= 0x7FFF:
                mapper = "ascii8"
                self._set_cart_mapper(m, cart_index, mapper)
                bank_registers[:] = m._default_cart_bank_registers(mapper)
            elif 0x6000 <= addr <= 0x67FF or 0x7000 <= addr <= 0x77FF:
                mapper = "ascii16"
                self._set_cart_mapper(m, cart_index, mapper)
                bank_registers[:] = m._default_cart_bank_registers(mapper)
            elif 0x8000 <= addr <= 0x9FFF:
                mapper = "konami"
                self._set_cart_mapper(m, cart_index, mapper)
                bank_registers[:] = m._default_cart_bank_registers(mapper)
            else:
                return False

        if mapper == "ascii8":
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

        if mapper == "generic8" or mapper == "zemina8":
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

        if mapper == "holy_quran":
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

        if mapper == "ascii16":
            if 0x6000 <= addr <= 0x6FFF:
                bank_registers[0] = value & 0xFF
                return True
            if 0x7000 <= addr <= 0x7FFF:
                bank_registers[1] = value & 0xFF
                return True
            return False

        if mapper == "harry_fox":
            if 0x6000 <= addr <= 0x6FFF:
                bank_registers[0] = 2 * (value & 0x01)
                return True
            if 0x7000 <= addr <= 0x7FFF:
                bank_registers[1] = (2 * (value & 0x01)) + 1
                return True
            return False

        if mapper == "generic16" or mapper == "zemina16":
            if 0x4000 <= addr <= 0x7FFF:
                bank_registers[0] = value & 0xFF
                return True
            if 0x8000 <= addr <= 0xBFFF:
                bank_registers[1] = value & 0xFF
                return True
            return False

        if mapper == "cross_blaim":
            bank_registers[1] = value & 0x03
            return True

        if mapper == "rtype":
            if 0x4000 <= addr <= 0x7FFF:
                if value & 0x10:
                    bank_registers[1] = value & 0x17
                else:
                    bank_registers[1] = value & 0x1F
                return True
            return False

        if mapper == "konami":
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

        if mapper == "konami_scc":
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

        segment = (addr - 0x4000) // 0x2000
        if segment < 0 or segment >= 4:
            return False
        bank_registers[segment] = value & 0xFF
        return True

    cdef void _set_cart_mapper(self, object m, int cart_index, object mapper):
        if cart_index == 1:
            m.cart1_mapper = mapper
        else:
            m.cart2_mapper = mapper
