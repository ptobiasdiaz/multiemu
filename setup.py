from setuptools import setup, Extension, find_packages
from Cython.Build import cythonize

extensions = [
    Extension("cpu.lr35902.bus", ["cpu/lr35902/bus.pyx"]),
    Extension("cpu.lr35902.core", ["cpu/lr35902/core.pyx"]),
    Extension("cpu.lr35902.memory", ["cpu/lr35902/memory.pyx"]),
    Extension("cpu.m6502.bus", ["cpu/m6502/bus.pyx"]),
    Extension("cpu.m6502.memory", ["cpu/m6502/memory.pyx"]),
    Extension("cpu.m6502.core", ["cpu/m6502/core.pyx"]),
    Extension("devices.gameboy.mbc1", ["devices/gameboy/mbc1.pyx"]),
    Extension("devices.gameboy.mbc2", ["devices/gameboy/mbc2.pyx"]),
    Extension("devices.gameboy.mbc3", ["devices/gameboy/mbc3.pyx"]),
    Extension("devices.gameboy.mbc5", ["devices/gameboy/mbc5.pyx"]),
    Extension("devices.gameboy.huc1", ["devices/gameboy/huc1.pyx"]),
    Extension("devices.gameboy.cartridge", ["devices/gameboy/cartridge.pyx"]),
    Extension("devices.gameboy.apu", ["devices/gameboy/apu.pyx"]),
    Extension("devices.gameboy.ppu", ["devices/gameboy/ppu.pyx"]),
    Extension("devices.gameboy.timer", ["devices/gameboy/timer.pyx"]),
    Extension("devices.gameboy.interrupts", ["devices/gameboy/interrupts.pyx"]),
    Extension("devices.gameboy.dma", ["devices/gameboy/dma.pyx"]),
    Extension("machines.frame_runner", ["machines/frame_runner.pyx"]),
    Extension("machines.m6502.vic20_io", ["machines/m6502/vic20_io.pyx"]),
    Extension("cpu.z80.memory", ["cpu/z80/memory.pyx"]),
    Extension("cpu.z80.io", ["cpu/z80/io.pyx"]),
    Extension("cpu.z80.bus", ["cpu/z80/bus.pyx"]),
    Extension("cpu.z80.core", ["cpu/z80/core.pyx"]),
    Extension("chipsets.ay38912_accel", ["chipsets/ay38912_accel.pyx"]),
    Extension("chipsets.ula_accel", ["chipsets/ula_accel.pyx"]),
    Extension("chipsets.via6522", ["chipsets/via6522.pyx"]),
    Extension("chipsets.vic6560", ["chipsets/vic6560.pyx"]),
    Extension("chipsets.vic6560_accel", ["chipsets/vic6560_accel.pyx"]),
    Extension("chipsets.cpc_gate_array_accel", ["chipsets/cpc_gate_array_accel.pyx"]),
    Extension("chipsets.cpc_crtc_accel", ["chipsets/cpc_crtc_accel.pyx"]),
    Extension("chipsets.cpc_ppi_accel", ["chipsets/cpc_ppi_accel.pyx"]),
    Extension("chipsets.cpc_render_accel", ["chipsets/cpc_render_accel.pyx"]),
    Extension("chipsets.cpc_video_accel", ["chipsets/cpc_video_accel.pyx"]),
]

setup(
    name="multiemu",
    version="0.2.3",
    description="Work-in-progress retro machine emulator in Python and Cython",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "multiemu=multiemu.cli:main",
        ],
    },
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            "language_level": 3,
            "boundscheck": False,
            "wraparound": False,
            "initializedcheck": False,
            "cdivision": True,
        },
    ),
    zip_safe=False,
)
