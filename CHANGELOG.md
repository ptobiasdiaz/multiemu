# Changelog

Este fichero resume hitos visibles del proyecto por versión publicada.

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
