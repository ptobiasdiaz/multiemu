# MultiEmu

`MultiEmu` es un multiemulador de máquinas retro escrito en Python y Cython.

La intención del proyecto es separar con claridad:

- CPU y partes críticas de rendimiento
- definición de máquinas y hardware
- frontends locales y remotos
- transporte y presentación en el CLI

El repositorio ya incluye soporte para máquinas ZX Spectrum, Amstrad CPC 464,
Nintendo Game Boy y una primera variante de Game Boy Color, además de
scaffolds iniciales para Amstrad CPC 664/6128, MOS KIM-1 y Commodore VIC-20. La
estructura sigue pensada para crecer hacia más máquinas y más frontends sin
mezclar toda la lógica en un único punto de entrada.

## Estado actual

Máquinas soportadas hoy:

- `spectrum16k`
- `spectrum48k`
- `cpc464` (experimental)
- `cpc664` (experimental)
- `cpc6128` (experimental)
- `gameboy` (experimental)
- `gameboycolor` / `gbc` (experimental)
- `kim1` (experimental)
- `vic20ntsc` (experimental)
- `vic20` (alias temporal de `vic20ntsc`)
- `vic20pal` (experimental)

Frontends y transportes disponibles hoy:

- `run --frontend pygame`
- `serve --transport tcp`
- `connect --transport tcp --frontend pygame`
- `debug --transport tcp --frontend tcp_debug`
- perfiles de display: `default`, `full-border`

El frontend también puede cargar un keymap externo con:

- `--keymap /ruta/al/keymap.json`

### Resumen de soporte por sistema

| Sistema | Estado | Vídeo | Audio | Teclado | Joystick | Cinta/Disco | Cartuchos/ROMs | Notas |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `spectrum16k` | usable | sí | beeper básico | sí | sí, hasta 2 | cinta `TZX/TAP` | ROM principal | soporte estable de arranque y carga básica |
| `spectrum48k` | usable | sí | beeper básico | sí | sí, hasta 2 | cinta `TZX/TAP` | ROM principal | base más madura del proyecto |
| `cpc464` | experimental | sí | AY básico | sí | sí, 1 | cinta `CDT/TZX`, disco `DSK` | ROM OS/BASIC/AMSDOS | timings y fidelidad aún incompletos |
| `cpc664` | experimental | sí | AY básico | sí | sí, 1 | disco `DSK` | ROM OS/BASIC/AMSDOS | reutiliza el scaffold CPC actual con ROMs 664 |
| `cpc6128` | experimental | sí | AY básico | sí | sí, 1 | disco `DSK` | ROM OS/BASIC/AMSDOS/expansion | RAM bancaria `128K` y scaffold 6128 inicial |
| `gameboy` | experimental | sí | sí | sí | pad del host | n/a | cartuchos `.gb`, mappers principales | buena base, no aún cobertura total del catálogo |
| `gameboycolor` / `gbc` | experimental | sí, con color | sí, aún algo lento | sí | pad del host | n/a | cartuchos `.gb`/`.gbc`, VRAM DMA, palettes CGB | doble velocidad y rendimiento aún por madurar |
| `kim1` | usable/experimental | display monitor | n/a | keypad/TTY | n/a | n/a | ROMs `6530` | monitor funcional |
| `vic20ntsc` | experimental avanzada | sí | sí, aún frágil | sí | sí, 1 | no | ROMs, `.prg`, carts crudos `.20/.40/.60/.a0` | la máquina 6502 más avanzada ahora mismo |
| `vic20pal` | experimental | sí | sí, aún frágil | sí | sí, 1 | no | ROMs, `.prg`, carts crudos `.20/.40/.60/.a0` | validado menos que NTSC |

Notas rápidas:

- `tcp` se usa hoy con `serve/connect`, no como `run --frontend tcp`.
- el modo debug remoto usa un runtime separado para no penalizar el loop normal.
- `vic20ntsc` y `vic20pal` arrancan ROMs y varios cartuchos reales, pero aún no tienen fidelidad completa de `VIC-I` ni audio cerrado.

## Debug remoto

El proyecto ya incluye un modo debug TCP separado del runtime normal. Ese modo:

- anuncia capacidades de debug en el `welcome`
- permite `pause`, `resume` y `step`
- permite descubrir dispositivos con `debug.list_devices`
- permite leer y escribir estado con `debug.get_state` y `debug.set_state`
- permite leer y escribir memoria con `debug.read_memory` y `debug.write_memory`

La semántica de hardware trazable está descrita en
[TRACEABLE_HARDWARE.md](/home/tobias/dev/multiemu/TRACEABLE_HARDWARE.md).

La extensión de protocolo TCP está descrita en
[DEBUG_PROTOCOL.md](/home/tobias/dev/multiemu/DEBUG_PROTOCOL.md).

Nota de arquitectura:

- el modo debug usa un loop distinto del loop rápido normal
- no se introduce un `if debug` dentro del hot path del runtime normal
- la pausa se hace efectiva en el borde de frame

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
  - `tape` -> `program.tzx`, `tape.tzx`
- `cpc464`
  - `os` -> `OS_464.ROM`
  - `basic` -> `BASIC_1.0.ROM`, `BASIC_1.1.ROM`, `BASIC_464.ROM`, `BASIC.ROM`, `cpc464.rom`
  - `tape` -> `program.cdt`, `tape.cdt`
- `cpc664`
  - `os` -> `OS_664.ROM`, `OS_664_BASIC_1.1.ROM`, `cpc664_os.rom`, `cpc664.rom`
  - `basic` -> `BASIC_1.1.ROM`, `BASIC_664.ROM`, `BASIC.ROM`, `cpc664_basic.rom`
  - `disk` -> `disk.dsk`, `program.dsk`
- `cpc6128`
  - `os` -> `OS_6128.ROM`, `OS_6128_BASIC_1.1.ROM`, `cpc6128_os.rom`, `cpc6128.rom`
  - `basic` -> `BASIC_1.1.ROM`, `BASIC_6128.ROM`, `BASIC.ROM`, `cpc6128_basic.rom`
  - `amsdos` -> `AMSDOS.ROM`, `amsdos.rom`
  - `disk` -> `disk.dsk`, `program.dsk`
  - `expansion` -> `expansion.rom`, `cart.rom`
- `gameboy`
  - `main` -> `gameboy.gb`, `cart.gb`
- `gameboycolor`
  - `main` -> `gameboy.gbc`, `cart.gbc`, `gameboy.gb`, `cart.gb`
- `kim1`
  - requiere `--rom lower=... --rom upper=...`
- `vic20ntsc`
  - `basic` -> `BASIC.901486-01.bin`, `vic20_basic.bin`, `vic20-basic.bin`
  - `kernal` -> `KERNAL.901486-07.bin`, `vic20_kernal.bin`, `vic20-kernal.bin`
  - `char` -> `CHAR.901460-03.bin`, `vic20_char.bin`, `vic20-char.bin`
  - `blk1` -> `vic20_blk1.bin`, `vic20-blk1.bin`
  - `blk2` -> `vic20_blk2.bin`, `vic20-blk2.bin`
  - `blk3` -> `vic20_blk3.bin`, `vic20-blk3.bin`
  - `blk5` -> `vic20_blk5.bin`, `vic20-blk5.bin`
- `vic20pal`
  - mismos slots y nombres por defecto que `vic20ntsc`

Puedes pasar ROMs explícitas con `--rom`:

- en máquinas con un solo slot, basta `--rom fichero`
- en máquinas con varios slots, usa `--rom slot=fichero`

Ejemplos:

```bash
multiemu run spectrum48k --rom spec48k.rom
multiemu run cpc464 --rom os=OS_464.ROM --rom basic=BASIC_1.0.ROM
multiemu run cpc664 --rom os=cpc664.rom
multiemu run cpc6128 --rom os=cpc6128.rom
multiemu run gameboy --rom game.gb
multiemu run gameboycolor --rom game.gbc
multiemu run kim1 --rom lower=6530-002.bin --rom upper=6530-003.bin
multiemu run vic20ntsc --rom basic=basic.bin --rom kernal=kernal.bin --rom char=char.bin
```

## Keymaps

Los frontends locales y remotos pueden usar keymaps externos en JSON.

La búsqueda de keymaps por id se hace hoy en este orden:

1. `$CWD/keymaps/`
2. `/usr/local/share/multiemu/keymaps`
3. `/usr/share/multiemu/keymaps`
4. `/etc/multiemu/keymaps`
5. `$HOME/.local/share/multiemu/keymaps`

Puedes forzar un fichero concreto con:

```bash
multiemu run spectrum128k --keymap ./mi_keymap.json --rom main=zx128k.rom
multiemu serve spectrum128k --keymap ./mi_keymap.json --rom main=zx128k.rom
multiemu connect --keymap ./mi_keymap.json
```

Los keymaps por defecto del proyecto viven en [keymaps/](/home/tobias/dev/multiemu/keymaps).
La guía para crear nuevos keymaps y mappings de joystick está en
[keymaps/README.md](/home/tobias/dev/multiemu/keymaps/README.md).

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

Nota sobre soporte de cinta:

- `spectrum16k` y `spectrum48k` aceptan un slot opcional `tape` en formato `TZX`
- `cpc464` acepta un slot opcional `tape` en formato `CDT/TZX`
- en el frontend `pygame`, `F1` hace `play/pause` de la cinta

## Tests

La suite del proyecto usa `pytest` y cubre:

- núcleo Z80
- máquinas Spectrum
- `cpc464`
- `gameboy`
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

Ejemplo para CPC664 con ROM combinada de `32K`:

```bash
multiemu run cpc664 --frontend pygame --rom os=cpc664.rom
```

Ejemplo para CPC6128 con ROM combinada y AMSDOS:

```bash
multiemu run cpc6128 --frontend pygame --rom os=cpc6128.rom --rom amsdos=amsdos.rom
```

Ejemplo para CPC con ROM de expansión:

```bash
multiemu run cpc464 --frontend pygame --rom os=OS_464.ROM --rom expansion=cart.rom
```

Ejemplo para Spectrum 48K con cinta:

```bash
multiemu run spectrum48k --frontend pygame --rom spec48k.rom --rom tape=program.tzx
```

Ejemplo para Game Boy:

```bash
multiemu run gameboy --frontend pygame --rom game.gb
```

Ejemplo para Game Boy Color:

```bash
multiemu run gameboycolor --frontend pygame --rom game.gbc
```

## Joysticks y gamepads

El frontend `pygame` ya puede mapear mandos del host a las máquinas que
exponen joystick/pad:

- `Spectrum`: hasta `2` joysticks
- `CPC464` / `CPC664`: `1` joystick
- `VIC-20`: `1` joystick
- `Game Boy` / `Game Boy Color`: el gamepad del host se traduce al `joypad`
  de la consola

En modo remoto TCP, un cliente puede elegir si su gamepad local controla el
primer o el segundo joystick emulado:

```bash
multiemu connect --joystick-player 1
multiemu connect --joystick-player 2
```

Eso permite conectar dos clientes a la misma instancia remota cuando la
arquitectura soporta dos joysticks.

Ejemplo para KIM-1:

```bash
multiemu run kim1 --frontend pygame --rom lower=6530-002.bin --rom upper=6530-003.bin
```

Ejemplo para VIC-20 NTSC:

```bash
multiemu run vic20ntsc --frontend pygame --rom basic=basic.bin --rom kernal=kernal.bin --rom char=char.bin
```

Ejemplo para VIC-20 PAL:

```bash
multiemu run vic20pal --frontend pygame --rom basic=basic.bin --rom kernal=kernal.bin --rom char=char.bin
```

## Uso básico de `kim1`

El frontend `pygame` usa un mapeo orientado al teclado numérico:

- `KP_0..KP_9` -> dígitos hexadecimales `0..9`
- `A..F` -> dígitos hexadecimales `A..F`
- `KP_MINUS` -> `ADDR`
- `KP_PERIOD` -> `DATA`
- `KP_PLUS` -> `STEP`
- `KP_ENTER` -> `RUN`
- `KP_DIVIDE` -> `PC`

Qué deberías ver:

- la pantalla muestra 6 dígitos hexadecimales
- en reposo, el monitor enseña la dirección o celda actualmente abierta
- si pulsas hexadecimales, modificas dirección o dato según el modo activo
- `ADDR` cambia a edición de dirección
- `DATA` cambia a edición de dato
- `STEP` avanza a la siguiente celda
- `RUN` salta a la dirección abierta
- `PC` muestra el contador de programa guardado por el monitor

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

Ejemplo equivalente para Game Boy:

```bash
multiemu serve gameboy --transport tcp --rom game.gb
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
