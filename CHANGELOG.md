# Changelog

Este fichero resume hitos visibles del proyecto por versión publicada.

## 0.2.9

Versión centrada en abrir `gamegear` como nueva máquina visible, reutilizando
la línea SMS2 pero cerrando las diferencias prácticas de pantalla, paleta,
puertos y audio estéreo.

### Incluye

- Nueva máquina visible `gamegear`.
- Soporte de cartuchos `.gg` como slot `main`, con heurística CLI de forma
  corta equivalente a SMS2.
- VDP compartido con SMS2 adaptado a Game Gear:
  - framebuffer visible `160x144`
  - recorte desde el área SMS-compatible
  - CRAM Game Gear de `64` bytes
  - paleta RGB de `12` bits
- Keymap propio de Game Gear:
  - cruceta
  - botones `1` y `2`
  - botón `START`
- Puertos específicos básicos de Game Gear:
  - `0x00` para `START` activo bajo
  - `0x01-0x05` como registros de link/serial retenidos
  - `0x06` como registro estéreo del PSG
- Audio estéreo real por máquina:
  - `BaseMachine` expone `audio_channels`
  - frontends pygame local y TCP respetan el número de canales de la máquina
  - Game Gear emite muestras intercaladas `L,R`
  - máquinas mono existentes siguen usando un canal
- `SN76489` ampliado:
  - registro estéreo Game Gear
  - render mono para SMS2
  - render estéreo intercalado para Game Gear
  - soporte práctico de periodo `0/1` como salida fija para samples/DAC por
    volumen usados por juegos reales
  - eliminación del filtrado interno que suavizaba en exceso efectos rápidos
- Mejoras de temporización de audio SMS/GG mediante oversampling interno del
  PSG y downsample final por frame.
- `F12`/`--state` preserva estado Game Gear, incluyendo `START`, registros IO
  básicos y estéreo PSG.

### Testing

- Nuevos tests para:
  - registro/CLI de `gamegear`
  - keymap y joystick `START`
  - recorte visible `160x144`
  - CRAM/paleta Game Gear de `12` bits
  - puertos `0x00-0x06`
  - audio estéreo intercalado Game Gear
  - separación entre SMS2 mono y Game Gear estéreo
  - `SN76489` estéreo frente a referencia Python
  - roundtrip de estado de `gamegear`
  - frontends local/TCP con número de canales por máquina

## 0.2.8

Versión centrada en abrir `mastersystem2`, madurar su VDP/PSG como chips
reutilizables y cerrar el soporte común de snapshots de estado por máquina.

### Incluye

- Nueva máquina visible `mastersystem2`.
- Soporte de cartuchos `.sms` y BIOS de Master System II, incluyendo:
  - arranque con BIOS sola
  - BIOS + cartucho
  - BIOS europea grande con juego built-in en bancos internos
  - selección de fuente ROM por control de memoria
- Nuevo VDP de Master System II en Cython, con referencia Python para tests:
  - VRAM/CRAM/registros
  - scroll horizontal y vertical
  - locks de scroll por zonas definidas por registros VDP
  - sprites, prioridad, zoom, colisión y overflow
  - interrupciones de línea y vblank
  - latch de estado de render en vblank
- Nuevo `SN76489` en Cython, con referencia Python para tests:
  - tonos
  - ruido periódico/blanco
  - mezcla básica
  - filtros prácticos para suavizar salida
  - estado serializable
- Keymap y joystick para `mastersystem2`, incluyendo segundo botón.
- Mejoras de temporización y audio por frame en SMS2.
- Soporte común de dump/carga de estado:
  - `F12` genera snapshot JSON
  - `--state <dump>` carga snapshots
  - cobertura de roundtrip para todas las máquinas actuales
- Trazabilidad de hardware ampliada para SMS2:
  - dispositivos debug `cartridge`, `mapper`, `ram`, `vdp` y `psg`
  - validación de tamaño/SHA256 de ROM, BIOS y built-in al restaurar estado
- Mejoras Z80 necesarias para software real:
  - `RRD`
  - `RLD`
  - ajuste de `EI`/interrupciones
  - opcodes `ED` no documentados tratados como NOP con warning
- Organización local de ROMs en `roms/<machine_id>/` e ignorado explícito de
  medios/artefactos locales.
- Ajustes de build para Python 3.13/setuptools/Cython en el entorno actual.

### Testing

- Nuevos tests para:
  - registro/CLI de `mastersystem2`
  - mapeo BIOS/cartucho/built-in
  - VDP SMS2 frente a referencia Python
  - `SN76489` frente a referencia Python
  - input y joystick SMS2
  - roundtrip de estado para todas las máquinas
  - dispositivos debug SMS2
  - validación de snapshots SMS2 contra ROM incompatible
  - opcodes Z80 `RRD`, `RLD`, `EI` y `ED` no documentados

## 0.2.7

Versión centrada en cerrar la línea Spectrum `128K/+2`, añadir snapshots
`.z80` como formato de entrada y simplificar la superficie interna del árbol.

### Incluye

- Nueva máquina visible `spectrumplus2`.
- Soporte inicial de snapshots `.z80` en:
  - `spectrum48k`
  - `spectrum128k`
  - `spectrumplus2`
- Restauración ampliada de estado `.z80` para Spectrum:
  - bancos RAM `48K` y `128K`
  - selección de ROM `48 BASIC` al restaurar snapshots `48K` sobre hardware `128K/+2`
  - `last_out_7ffd`
  - registros `AY`
  - posición básica dentro del frame
- Ajustes prácticos de ejecución para snapshots Spectrum:
  - mejor momento de entrega de IM1 por frame en la ULA
  - conservación correcta del bit alto del registro `R` del Z80
- Separación explícita de keymaps Spectrum por máquina:
  - `spectrum48k`
  - `spectrum128k`
- Simplificación interna del árbol:
  - eliminación de wrappers triviales en `chipsets/`
  - desaparición del sufijo `_accel` en los módulos canónicos exportados

### Testing

- Nuevos tests para:
  - snapshots `.z80` `48K`, `128K` y `+2`
  - restauración de RAM `48K` sobre hardware `128K/+2`
  - despertar de `HALT` por interrupción Spectrum dentro del frame
  - preservación del bit alto de `R` en el Z80

## 0.2.6

Versión centrada en abrir `spectrum128k` como nueva variante visible y en
hacer el sistema de keymaps más flexible y configurable desde ficheros JSON.

### Incluye

- Nueva máquina `spectrum128k` como variante visible del árbol Spectrum.
- Primer bloque funcional de `128K` para Spectrum con:
  - ROM dual de `32K` o ROM única de `16K`
  - paginación por `0x7FFD`
  - RAM de `128K` en `8` bancos de `16K`
  - conmutación de banco de pantalla para la ULA
  - soporte básico de `AY-3-8912`
- Corrección de writes a espacio ROM en `Spectrum 128K`: ahora se ignoran en
  vez de romper la emulación.
- Revisión práctica del teclado `128K` para menú/editor, incluyendo:
  - cursores
  - `Backspace`
  - `,`, `.`
  - símbolos como `+`, `-`, `/`, `=`
- Nuevo sistema de keymaps externos en `keymaps/`, con soporte para:
  - `keys`
  - `combos`
  - `unicode_combos`
  - `gamepad`
- Nuevo parámetro `--keymap` en CLI para:
  - `run`
  - `serve`
  - `debug`
  - `connect`
  - `client`
- Keymaps Spectrum separados por máquina:
  - `spectrum48k`
  - `spectrum128k`
- Runtime remoto preparado para enviar un `keymap_spec` serializado cuando el
  servidor se lanza con un keymap personalizado.
- Búsqueda de keymaps alineada con rutas de sistema:
  - `$CWD/keymaps`
  - `/usr/local/share/multiemu/keymaps`
  - `/usr/share/multiemu/keymaps`
  - `/etc/multiemu/keymaps`
  - `$HOME/.local/share/multiemu/keymaps`

### Testing

- Nuevos tests para:
  - `Spectrum 128K` en registro/CLI y paginación básica
  - keymaps externos por fichero
  - `keymap_spec` en el cliente TCP
  - símbolos y atajos del editor `128K`

## 0.2.5

Versión centrada en ampliar la familia CPC con `cpc6128` y en seguir cerrando
la ergonomía práctica del scaffold CPC actual.

### Incluye

- Nueva máquina `cpc6128` como variante visible del árbol.
- Primer bloque funcional de RAM bancaria de `128K` para `cpc6128`.
- Soporte de ROM combinada `OS+BASIC` de `32K` también para `cpc6128`.
- Renderer CPC ajustado para tolerar RAM bancaria del `6128`.
- Soporte de slot `expansion` en `cpc464`, `cpc664` y `cpc6128`.
- Aceptación automática de ROMs CPC de `16K + 128 bytes` con cabecera
  AMSDOS en slots `basic`, `amsdos` y `expansion`.
- Parser `DSK` ampliado para aceptar otra variante válida de cabecera CPCEMU.
- `FDC` CPC más cercano al comportamiento esperado por AMSDOS durante
  lecturas de directorio y lecturas multisector.
- Ajuste del keymap CPC para poder introducir `|` desde layouts de host donde
  `AltGr+1` es la combinación natural.

### Testing

- Nuevos tests de registro/CLI para `cpc6128`.
- Nuevos tests para RAM bancaria y scaffold inicial del `6128`.
- Cobertura adicional para:
  - slot `expansion`
  - ROMs CPC con cabecera AMSDOS
  - parser `DSK`
  - `FDC` CPC

## 0.2.4

Versión centrada en cerrar el primer bloque común de joystick/pad para las
máquinas actuales y en añadir `cpc664` como nueva variante visible del árbol.

### Incluye

- Soporte común de `joystick/pad` en frontends locales y remotos.
- Protocolo TCP remoto ampliado para anunciar y transportar estado de:
  - `joystick_0`
  - `joystick_1`
- Cliente remoto `pygame` con selección de jugador para joystick mediante:
  - `--joystick-player 1`
  - `--joystick-player 2`
- Soporte de joystick cerrado en las máquinas actuales donde aplica:
  - `spectrum16k` / `spectrum48k`: hasta `2` joysticks
  - `cpc464`: `1` joystick
  - `vic20ntsc` / `vic20pal`: `1` joystick
- El `VIC-20` deja de usar un overlay de teclado para joystick y pasa a una
  ruta más cercana al hardware real a través de `VIA1` y `VIA2`.
- Nueva máquina `cpc664` como variante del scaffold CPC actual.
- Carga de ROM combinada `OS+BASIC` de `32K` para `cpc464` y `cpc664`,
  incluyendo el caso práctico de `cpc664.rom`.

### Testing

- Nuevos tests para:
  - mapping de gamepad a joystick en `pygame`
  - cliente TCP con preferencia de jugador de joystick
  - estado combinado de teclado + joystick en runtime remoto
  - wiring de joystick en `Spectrum`, `CPC` y `VIC-20`
- Nuevos tests de CLI/registro para `cpc664` y para ROM combinada de `32K`.

## 0.2.3

Versión centrada en abrir una primera infraestructura de depuración remota y en
hacer que el hardware emulado sea trazable de forma consistente.

### Incluye

- Nuevo runtime/frontend de debug TCP separado del frontend remoto normal.
- Extensión de protocolo debug sobre TCP con soporte para:
  - `pause`
  - `resume`
  - `step`
  - `list_devices`
  - `get_state`
  - `set_state`
  - `read_memory`
  - `write_memory`
- Nuevo `DebugSession` común para stepping e inspección de máquina.
- Contrato estable de hardware trazable:
  - `read_state()`
  - `write_state()`
  - `debug_devices()` con `device_id` estables
- Cobertura de estado ampliada a CPUs, buses, memorias y chips/dispositivos
  principales activos del árbol, incluyendo:
  - `Game Boy` y `Game Boy Color`
  - `VIC-20`
  - `Spectrum`
  - `CPC`
  - `KIM-1`
- Documentación nueva para:
  - contrato de hardware trazable
  - protocolo remoto de debug

### Testing

- Nuevos tests para `DebugSession`.
- Nuevos tests para el frontend TCP de debug.
- Cobertura adicional para inventario de dispositivos depurables y roundtrip de
  estado en hardware activo.

## 0.2.2

Versión centrada en abrir `gameboycolor` como variante visible y en cerrar el
primer bloque funcional real de hardware `CGB` sobre la base previa de
`gameboy`.

### Incluye

- Nueva máquina `gameboycolor` con alias `gbc`.
- Primer bloque funcional de hardware `CGB`:
  - `KEY1` y cambio de velocidad con `STOP`
  - banking de `VRAM` y `WRAM` mediante `VBK` y `SVBK`
  - paletas CGB (`FF68-FF6B`)
  - atributos de tile y selección de banco en `PPU`
  - soporte inicial de `GDMA` y `HDMA`
- Correcciones del `PPU` CGB para:
  - prioridad de sprites por índice de `OAM`
  - semántica de `LCDC.0` en modo `CGB`
  - fetch correcto de tiles desde `VRAM bank 1`
- Optimización importante de rendimiento en Game Boy / Game Boy Color:
  - hot path del `LR35902`
  - bus tipado en Cython
  - `PPU` con rutas rápidas para `VRAM/OAM` y scheduler interno más barato
  - `APU` con pasos de fase precalculados por canal
- Limpieza adicional de arquitectura:
  - eliminación de capas base vacías en varias familias
  - mejora del bus `m6502` con lookup paginado más barato

### Testing

- Nuevos tests para `CGB`:
  - `KEY1` + `STOP`
  - `VBK` / `SVBK`
  - paletas CGB
  - atributos y bancos de tile
  - `GDMA` / `HDMA`
- Cobertura adicional para prioridades de `PPU` CGB y acceso a `VRAM` por
  banco.

## 0.2.1

Versión en desarrollo centrada en abrir `vic20ntsc` como siguiente máquina
6502 real y en seguir cerrando lagunas del Z80 detectadas al ejecutar software
más exigente.

### Incluye

- Nueva máquina `vic20ntsc` como variante explícita del Commodore VIC-20 NTSC,
  con `vic20` mantenido como alias temporal, y nueva variante `vic20pal`.
- Primer bloque funcional del `VIC-I` (`6560`) y del `VIA6522` para el
  arranque real de ROMs/cartuchos del VIC-20.
- Soporte inicial de cartuchos `VIC-20` tanto en formato `.prg` como en ROM
  autostart cruda de `BLK5`, incluyendo autoload de cartuchos `16K`
  partidos entre `BLK3 + BLK5`.
- Soporte adicional de imágenes crudas de cartucho `VIC-20` por extensión:
  - `.20`
  - `.40`
  - `.60`
  - `.a0`
- Nuevos opcodes/casos `DD/FD` del Z80 necesarios para software real:
  - `EX (SP),IX/IY`
  - ALU sobre `IXH/IXL` e `IYH/IYL`
  - fallback correcto para opcodes `DD/FD` no afectados por el prefijo
- Fallback de opcodes `ED` no documentados del Z80 como `NOP` temporizado,
  incluyendo `ED ED`.
- `VIA6522` y `VIC-I` (`6560`) convertidos en implementaciones canónicas en
  Cython, con referencias Python movidas a `tests/fallbacks/` cuando aplica.
- `M6502Bus` y `memory` del `m6502` cythonizados como implementación activa.
- `memory` del `LR35902` cythonizada como implementación activa.
- Mejora visible de rendimiento del `VIC-20` al mover a Cython:
  - fetch visible del `VIC-I`
  - RAM de color e I/O pequeña del `VIC-20`
  - partes del render por scanline
- Frontend remoto `tcp` estabilizado:
  - `serve` y `connect` ya toleran `fps_limit=None`
  - cliente `tcp + pygame` arreglado para handshakes con `fps: null`
- `Spectrum` vuelve a anunciar `50 fps` como objetivo en frontend local y
  remoto.

### Testing

- Cobertura nueva de `vic20ntsc` para vídeo, teclado, cartuchos, timing del
  `VIC-I` y semántica del `VIA6522`.
- Nuevos tests de Z80 para `EX (SP),IX/IY` y para el comportamiento de
  prefijos `DD/FD` ignorados cuando el opcode no se ve afectado.
- Nuevos tests de CLI/registro para cartuchos VIC-20 crudos `.20`.
- Nuevos tests para runtime remoto TCP y handshake del cliente `pygame`.

## 0.2.0

Versión centrada en abrir la familia `m6502`, consolidar `KIM-1` como primera
máquina 6502 usable, y separar chipsets internos de periféricos y medios.

### Incluye

- Nueva familia `m6502` y primera máquina real `kim1`.
- Core `m6502` acelerado en Cython como implementación canónica del paquete.
- Referencia Python del `m6502` movida a `tests/fallbacks/` para tests de
  equivalencia accel/reference.
- Soporte del monitor `KIM-1` con carga explícita de `6530-002` y `6530-003`.
- Implementación funcional del `M6530` para:
  - display escaneado
  - keypad
  - timer e IRQ
  - entrada/salida TTY bit-bang
- Validación del monitor real del `KIM-1` sobre ROMs originales en rutas de:
  - `ADDR`
  - `DATA`
  - `STEP`
  - `PC`
  - `RUN`
  - `OPEN`
  - `MODIFY`
  - `GOEXEC`
  - `OUTCH`
  - `DUMP`
  - `LOAD`
- Soporte básico de disco para `cpc464`:
  - parser de imágenes `DSK`
  - FDC mínimo
  - slot `disk`
  - slot `amsdos`
- Soporte de cinta `TAP` para Spectrum además de `TZX`.
- Introducción del namespace `chipsets/` como espacio canónico para chips y
  subsistemas internos, separándolos de medios/periféricos en `devices/`.

### Testing

- Nuevos tests para `m6502` y equivalencia entre referencia Python y core
  Cython.
- Nuevos tests de monitor real para `KIM-1`, incluyendo rutas TTY y
  roundtrip `DUMP -> LOAD`.
- Nuevos tests para parser/FDC de disco CPC.
- Cobertura adicional para `Spectrum .tap`.
- Ajustes de tests e imports para el nuevo namespace `chipsets/`.

## 0.1.2

Versión centrada en ampliar cobertura real de Game Boy y cintas, y en cerrar
algunas lagunas de CPU/CLI detectadas al probar software más exigente.

### Incluye

- Soporte inicial de mapper `HuC1` en Game Boy, con banking e IR stub.
- Stub de puerto serie de Game Boy (`SB/SC`) integrado en la máquina base.
- Soporte de slot de cinta opcional en `spectrum16k`, `spectrum48k` y `cpc464`.
- Registro visible de `gameboy` en la CLI con carga corta de `--rom` para el
  cartucho principal.
- Nuevos keymaps y señales de backend para control básico de cinta desde el
  frontend.
- Nuevas implementaciones Z80 para block I/O `INI/INIR/IND/INDR/OUTI/OTIR/OUTD/OTDR`
  y cargas indexadas `DD/FD` que faltaban.

### Testing

- Nuevos tests de equivalencia accel/reference para `HuC1` y LR35902.
- Cobertura adicional de Game Boy para `STOP`, puerto serie, `HuC1` y smoke
  ROMs opcionales.
- Nuevos tests de parsing y entrada de cinta para CPC y Spectrum.
- Cobertura adicional para opcodes Z80 y para IRQs/audio progresivo en CPC.

## 0.1.1

Versión centrada en mejorar la ergonomía del frontend local y la integración
de CI.

### Incluye

- Cambio a pantalla completa en el frontend `pygame` mediante `Alt + Enter`
- Cobertura específica para el toggle de pantalla completa
- Ajustes de CI para ejecutar `tox` en GitHub Actions con versiones actuales
  de las actions y sin empaquetado previo del proyecto

## 0.0.3

Versión centrada en consolidar la arquitectura común de ejecución entre
máquinas y en validar compatibilidad real con software Game Boy, CPC y
Spectrum.

### Incluye

- `Machine Runner` común en Python/Cython para unificar el frame loop de:
  - `gameboy`
  - `spectrum16k`
  - `spectrum48k`
  - `cpc464`
- Game Boy mucho más avanzada a nivel funcional:
  - mappers `MBC2` y `MBC5`
  - mejoras relevantes del APU (`wave`, `noise`, `sweep`)
  - mejoras de PPU y DMA
- Cythonización de los bloques calientes de Game Boy:
  - CPU LR35902
  - bus
  - PPU
  - APU
  - timer
  - cartridge y mappers principales
- Soporte inicial de cinta `CDT/TZX` para `cpc464`, validado con
  `dawn-of-kernel.cdt`
- Soporte inicial de cinta `TZX` para `spectrum48k`, validado con
  `phantomasa-48k.tzx`
- Control manual de `play/pause` de cinta con `F1` en el frontend `pygame`

### Compatibilidad y correcciones

- Corrección de regresiones de audio al integrar el runner común en Spectrum.
- Corrección de un `OverflowError` en el runner Cython compartido.
- Implementación de opcodes Z80 faltantes necesarios para software real,
  incluyendo:
  - familia `ED` de block I/O (`INI/INIR/IND/INDR/OUTI/OTIR/OUTD/OTDR`)
  - cargas indexadas `DD/FD` como `DD 68`
- Ajustes en vídeo y audio de CPC a partir de pruebas con software real.
- Soporte de CLI ampliado para slots de cinta opcionales en máquinas con tape.

### Testing

- Nuevas pruebas de equivalencia para componentes acelerados de Game Boy.
- Cobertura del `Machine Runner` compartido.
- Nuevos tests de cinta para CPC y Spectrum.
- Cobertura adicional para opcodes Z80 que estaban faltando en ejecución real.

### Máquinas soportadas

- `spectrum16k` - ZX Spectrum 16K
- `spectrum48k` - ZX Spectrum 48K
- `cpc464` - Amstrad CPC 464 (experimental)
- `gameboy` - Nintendo Game Boy (experimental)

## 0.0.2

Versión centrada en consolidar el soporte experimental de `cpc464` y en
convertir la base de tests en una suite de `pytest` más útil para desarrollo y
regresión.

### Incluye

- Soporte visible de `cpc464` en la CLI y en la documentación del proyecto.
- Arquitectura del CPC más cercana a la del Spectrum: máquina en Python e
  implementación acelerada de los chips y subsistemas principales.
- Ruta principal de vídeo basada en `rgb24` tanto para Spectrum como para CPC.
- Frontend local `pygame` y cliente/servidor TCP preparados para consumir
  `rgb24` de forma directa.
- Integración inicial del AY-3-8912 dentro del CPC con generación de audio por
  frame.
- Corrección del avance temporal del Z80 en estado `HALT`, necesaria para no
  acelerar artificialmente software que espera por interrupciones.

### Testing

- Sustitución de antiguos pseudo-tests/manual tests por tests reales de
  `pytest`.
- Fallbacks Python de referencia movidos a `tests/fallbacks/` para comparar
  comportamiento frente a las implementaciones aceleradas.
- Nuevos tests de equivalencia entre rutas accel y referencias para ULA,
  render/vídeo CPC, chips base del CPC y AY-3-8912.
- Cobertura específica para Spectrum, CPC464 y núcleo Z80 más estable y más
  orientada a regresión automática.

### Máquinas soportadas

- `spectrum16k` - ZX Spectrum 16K
- `spectrum48k` - ZX Spectrum 48K
- `cpc464` - Amstrad CPC 464 (experimental)

## 0.0.1

Primera versión pública del proyecto como base de trabajo del multiemulador.

### Incluye

- Núcleo Z80 en Python/Cython con capacidad suficiente para arrancar ROMs de Spectrum.
- Capa de máquinas separada de la CPU para facilitar nuevas variantes y familias futuras.
- CLI `multiemu` con comandos para listar máquinas, ejecutar localmente, servir sesiones remotas y conectarse a ellas.
- Búsqueda automática de ROMs por rutas estándar del sistema cuando no se pasa `--rom`.

### Máquinas soportadas

- `spectrum16k` - ZX Spectrum 16K
- `spectrum48k` - ZX Spectrum 48K

### Frontends y transportes disponibles

- Frontend local: `pygame`
- Transporte de servidor remoto: `tcp`
- Transporte de conexión remota: `tcp`
- Frontend gráfico para `connect`: `pygame`

### Notas

- `client` se mantiene como alias de `connect`.
- La combinación remota disponible en esta versión es `tcp + pygame`.
- El servidor captura `Ctrl-C` y cierra de forma limpia.
