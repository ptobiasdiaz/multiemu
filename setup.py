from setuptools import setup, Extension, find_packages
from Cython.Build import cythonize

extensions = [
    Extension("cpu.z80.memory", ["cpu/z80/memory.pyx"]),
    Extension("cpu.z80.io", ["cpu/z80/io.pyx"]),
    Extension("cpu.z80.bus", ["cpu/z80/bus.pyx"]),
    Extension("cpu.z80.core", ["cpu/z80/core.pyx"]),
    Extension("devices.ula_accel", ["devices/ula_accel.pyx"]),
]

setup(
    name="multiemu",
    version="0.1.0a1",
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
