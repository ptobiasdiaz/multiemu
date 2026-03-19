# MultiEmu

`MultiEmu` es un multiemulador de máquinas retro escrito en Python y Cython.

La intención del proyecto es separar con claridad:

- CPU y partes críticas de rendimiento
- definición de máquinas y hardware
- frontends locales y remotos
- transporte y presentación en el CLI

El repositorio ya incluye soporte para máquinas ZX Spectrum y un soporte
experimental de Amstrad CPC 464. La estructura sigue pensada para crecer hacia
más máquinas y más frontends sin mezclar toda la lógica en un único punto de
entrada.

## Estado actual

Máquinas soportadas hoy:

- `spectrum16k`
- `spectrum48k`
- `cpc464` (experimental)

Frontends y transportes disponibles hoy:

- `run --frontend pygame`
- `serve --transport tcp`
- `connect --transport tcp --frontend pygame`
- perfiles de display: `default`, `full-border`

## Requisitos

- Python 3.13
- compilador C
- entorno gráfico compatible con `pygame` para las pruebas visuales

## Instalación con `venv`

Crear y activar un entorno virtual:

```bash
python3 -m venv .venv
. .venv/bin/activate
```

Actualizar herramientas base e instalar el proyecto en editable:

```bash
python -m pip install --upgrade pip setuptools wheel Cython
python -m pip install -e .
python setup.py build_ext --inplace
```

Si vas a usar los frontends con ventana gráfica, instala también las
dependencias opcionales:

```bash
python -m pip install pygame numpy
```

## ROMs

Si no pasas ninguna opción `--rom`, `multiemu` buscará automáticamente las ROMs requeridas en
este orden:

1. directorio actual
2. `$HOME/.local/share/multiemu/`
3. `/usr/local/share/multiemu/roms/`
4. `/usr/share/multiemu/`

Slots y nombres esperados por defecto:

- `spectrum16k`
  - `main` -> `spec16k.rom`
- `spectrum48k`
  - `main` -> `spec48k.rom`
- `cpc464`
  - `os` -> `OS_464.ROM`
  - `basic` -> `BASIC_1.0.ROM`, `BASIC_1.1.ROM`, `BASIC_464.ROM`, `BASIC.ROM`, `cpc464.rom`

Puedes pasar ROMs explícitas con `--rom`:

- en máquinas con un solo slot, basta `--rom fichero`
- en máquinas con varios slots, usa `--rom slot=fichero`

Ejemplos:

```bash
multiemu run spectrum48k --rom spec48k.rom
multiemu run cpc464 --rom os=OS_464.ROM --rom basic=BASIC_1.0.ROM
```

Nota sobre `cpc464`:

- el soporte actual es todavía experimental
- implementa el mapa de memoria CPC con ROM baja/alta sobre 64 KB de RAM
- incluye un Gate Array mínimo para modo, tintas, borde y control de ROM
- incluye un CRTC mínimo con render aproximado desde VRAM
- incluye teclado CPC básico mediante matriz 10x8 leída por PPI/PSG
- incluye una primera integración del PSG AY-3-8912 con salida de audio
- todavía no tiene timings de vídeo completos ni fidelidad de audio CPC cerrada
- para un arranque razonable del CPC464 necesitas también la ROM alta de BASIC
- el cargador intenta localizar automáticamente una ROM BASIC compatible, por ejemplo `BASIC_1.0.ROM`
- si sólo está `OS_464.ROM`, el sistema puede terminar ejecutando RAM y mostrar imagen corrupta

## Tests

La suite del proyecto usa `pytest` y cubre:

- núcleo Z80
- máquinas Spectrum
- `cpc464`
- equivalencia entre implementaciones aceleradas y referencias Python

Ejemplo:

```bash
./.venv/bin/python -m pytest -q
```

## Ver máquinas disponibles

```bash
multiemu list-machines
```

## Ver perfiles de display disponibles

```bash
multiemu list-display-profiles
```

## Prueba standalone

Ejecutar una máquina localmente con ventana `pygame`:

```bash
multiemu run spectrum48k --frontend pygame --rom spec48k.rom
```

Si la ROM está en una de las rutas de búsqueda por defecto, basta con:

```bash
multiemu run spectrum48k
```

Ejemplo para Spectrum 16K:

```bash
multiemu run spectrum16k --frontend pygame --rom spec16k.rom
```

Ejemplo con un perfil de display distinto:

```bash
multiemu run spectrum48k --display-profile full-border
```

Ejemplo para CPC464 con ROMs explícitas:

```bash
multiemu run cpc464 --frontend pygame --rom os=OS_464.ROM --rom basic=BASIC_1.0.ROM
```

El perfil de display también puede aplicarse al servidor remoto, porque el
framebuffer se genera en la máquina servida:

```bash
multiemu serve cpc464 --display-profile full-border --rom os=OS_464.ROM --rom basic=BASIC_1.0.ROM
```

## Prueba con `serve` y dos clientes

### 1. Arrancar el servidor

En una primera terminal:

```bash
multiemu serve spectrum48k --transport tcp --host 127.0.0.1 --port 8765 --rom spec48k.rom
```

Si la ROM está en una ruta conocida:

```bash
multiemu serve spectrum48k --transport tcp --host 127.0.0.1 --port 8765
```

El servidor captura `Ctrl-C` y cierra limpiamente.

### 2. Conectar el primer cliente

En una segunda terminal:

```bash
multiemu connect --transport tcp --frontend pygame --host 127.0.0.1 --port 8765 --title "MultiEmu Client 1"
```

### 3. Conectar el segundo cliente

En una tercera terminal:

```bash
multiemu connect --transport tcp --frontend pygame --host 127.0.0.1 --port 8765 --title "MultiEmu Client 2"
```

También puedes usar el alias `client`:

```bash
multiemu client --transport tcp --frontend pygame --host 127.0.0.1 --port 8765
```

## Qué esperar en la prueba remota

- los clientes reciben vídeo y audio desde la misma sesión remota
- el teclado se fusiona entre clientes por frame
- ambos clientes interactúan sobre la misma máquina emulada

## Desarrollo

El punto de entrada principal para usuario es:

- `multiemu`

La lógica del CLI está separada en:

- `multiemu/cli.py`
- `multiemu/machine_registry.py`
- `multiemu/runtime_registry.py`
- `multiemu/remote_runtime.py`

Esto permite añadir nuevas máquinas, transportes o frontends con menos
acoplamiento que si todo viviera dentro de scripts sueltos.
