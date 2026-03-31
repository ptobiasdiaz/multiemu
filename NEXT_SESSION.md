# Session Save

Fecha de actualización: 2026-03-27T00:00:00+01:00

Este fichero es un punto de reentrada para la próxima sesión. No sustituye a
`CONTEXT.md`: aquí va estado táctico, no decisiones duraderas.

## Punto exacto actual

El foco principal de `0.2.1` sigue siendo `vic20ntsc`, pero el trabajo de
fidelidad ya está en un punto donde compensa empezar la primera
Cythonización selectiva.

Estado real:

- `m6502` sigue estable y ya no es el cuello de botella principal
- `KIM-1` sigue estable y verificado
- `vic20ntsc` ya arranca ROMs reales, renderiza vídeo útil, acepta cartuchos,
  tiene teclado funcional en BASIC y un `VIA6522` bastante más maduro

La máquina canónica actual es:

- `vic20ntsc`

Y se mantiene:

- `vic20` como alias compatible

## Estado actual de VIC-20

Archivos clave:

- máquina:
  - [vic20.py](/home/tobias/dev/multiemu/machines/m6502/vic20.py)
- `VIA`:
  - [via6522.py](/home/tobias/dev/multiemu/chipsets/via6522.py)
- `VIC-I`:
  - [vic6560.py](/home/tobias/dev/multiemu/chipsets/vic6560.py)
- registro/loader:
  - [machine_registry.py](/home/tobias/dev/multiemu/multiemu/machine_registry.py)
- tests:
  - [test_vic20.py](/home/tobias/dev/multiemu/tests/test_vic20.py)
  - [test_via6522.py](/home/tobias/dev/multiemu/tests/test_via6522.py)
  - [test_keymaps.py](/home/tobias/dev/multiemu/tests/test_keymaps.py)
  - [test_cli.py](/home/tobias/dev/multiemu/tests/test_cli.py)

Qué funciona ya:

- arranque real a BASIC con:
  - `basic.901486-01.bin`
  - `kernal.901486-07.bin`
  - `characters.901460-03.bin`
- vídeo utilizable con:
  - screen RAM
  - char ROM/RAM visible al `VIC-I`
  - color RAM
  - multicolor por carácter
  - `8x8` y `8x16`
- dos `VIA 6522` cableados:
  - `VIA1` en `0x9110` a `NMI`
  - `VIA2` en `0x9120` a `IRQ`
- teclado matricial por `VIA2`, usable en BASIC
- audio básico del `VIC-I` ya existe, pero no debe usarse aún como señal de
  corrección porque la máquina sigue por debajo de tiempo real en Python
- `cart` acepta:
  - `.prg` en `BLK1/2/3/5`
  - ROM autostart cruda `BLK5` con firma `A0CBM`
- autoload de cartucho `16K` partido en `6000 + a000`
- soporte explícito de RAM de cartucho en:
  - `IO2` (`0x9800-0x9BFF`)
  - `IO3` (`0x9C00-0x9FFF`)
  para cartuchos de diagnóstico

## Ajustes recientes importantes

### VIC-I

Correcciones ya hechas y ya consolidadas:

- tabla específica de `char_base()` para `9005`
- fetch visible del `VIC-I` separado de la vista de CPU
- `screen codes` altos en `8x16` tratados como índices reales de `8 bits`
- `screen code` bit 7 como reverse solo en `8x8`
- multicolor corregido a:
  - `00 -> background`
  - `01 -> border`
  - `10 -> auxiliary`
  - `11 -> color por celda`
- no aplicar `reverse` sobre celdas multicolor antes de decodificar pares
- clipping del renderer para no romper `pygame`
- timing/fetch visible más cercano a `VICE`
  - ventana de fetch separada de la ventana visible
  - eventos finos anclados al fetch y no al borde visible
  - fetch por scanline en vez de por fila de texto
- el hot path del renderer ya no recompone semántica de vídeo:
  - `VIC-I` expone contexto visible por scanline
  - el contexto ya incluye `screen_code`, `color_nibble`, `glyph_addr`,
    `glyph_bits`, `reg_e/reg_f`, modo efectivo y fases de foreground
  - el renderer queda muy cerca de ser un consumidor de fetch + blitter `rgb24`

Resultado práctico:

- `Spider City.NTSC.prg` es ya casi jugable, aunque sigue teniendo glitches
- `Videomania.prg` sigue avanzando poco y parece quedarse en self-test

### VIA 6522

Cambios recientes ya consolidados:

- líneas `CA1/CA2/CB1/CB2`, `PCR`, handshake/pulse y latches de puerto
- `PRA` frente a `PRA_NHS`
- `SR` con modos `CB1`, `PHI2`, `T2` y free-running
- control de `CB1/CB2` por el propio `SR`
- `PB7` gobernado por `T1`
- `T1`:
  - one-shot con paso por `FFFF` y recarga desde latch
  - free-running con varios underflows por ráfaga bien resueltos
- `T2`:
  - continuidad desde `FFFF` tras underflow
  - interacción `T2/SR` más cercana a `VICE` con secuencia
    `underflow -> post-underflow -> reload -> shift`

Conclusión práctica:

- `VIA6522` ya no parece bloquear la primera Cythonización
- el único frente aún delicado sería afinar más `T2/SR` si aparece un caso real
  que lo exija

### Diagnóstico VIC-20

Cartuchos disponibles:

- [roms/diag-vic20.bin](/home/tobias/dev/multiemu/roms/diag-vic20.bin)
- [roms/vc-20-diag.324173-01.bin](/home/tobias/dev/multiemu/roms/vc-20-diag.324173-01.bin)

Lectura actual:

- `diag-vic20.bin` es la referencia útil para `vic20ntsc`
- `vc-20-diag.324173-01.bin` probablemente corresponde a otra variante y no es
  buena referencia para el modelo actual

Estado observado en `diag-vic20.bin`:

- en pantalla llega al menos a:
  - `RAM TEST`
  - `COLOR RAM TEST`
  - `ROMCHECK`
- internamente no hay evidencia de fallo de checksum:
  - el algoritmo del cartucho cuadra con las ROMs reales
  - `BASIC -> C0`
  - `KERNAL -> E0`
  - `CHAR -> FF`
- el cartucho pasa muchísimo tiempo en tests largos de RAM y luego en el bucle
  real del checksum de ROM
- la sensación de “se queda en ROMCHECK” parece deberse más a duración/rendimiento
  de la prueba que a un fallo semántico ya demostrado

Conclusión táctica:

- no tomar `diag-vic20.bin` como blocker inmediato del desarrollo del `VIC-I`
- usarlo como smoke de largo recorrido y como guía cuando falle algo estructural

## Cartuchos reales probados

ROMs locales útiles en [roms/](/home/tobias/dev/multiemu/roms):

- `Spider City.NTSC.prg`
- `Videomania.prg`
- `Amazin Maze.prg`
- `AE-6000.prg`
- `AE-a000.prg`

Estado observado:

- `Spider City.NTSC.prg`
  - casi jugable
  - las mejoras recientes del `VIC-I` han reducido glitches y flashazos
  - sigue siendo el mejor cartucho guía para iterar vídeo
- `Videomania.prg`
  - parece ejecutar un self-test y no pasar de ahí
  - no debe ser ahora mismo el cartucho guía principal
- `Amazin Maze.prg`
  - se dibuja correctamente
  - el mensaje del propio cartucho indica uso de cursores
  - la entrada aún no coincide del todo con lo que espera el juego
- `AE-6000.prg` + `AE-a000.prg`
  - cargan correctamente como cartucho `16K`
  - no es buen cartucho guía para esta fase; probablemente mezcla requisitos
    extra de expansión/memoria

## Qué está pendiente de verdad

El siguiente trabajo útil ya no es más loader ni más refino previo:
es abrir la primera Cythonización selectiva del `VIC-I`.

Prioridad recomendada:

1. Cythonizar el hot path del `VIC-I`
2. mantener la referencia Python actual como semántica visible
3. usar `Spider City.NTSC.prg` y la suite de tests como oráculo de regresión
4. dejar `diag-vic20.bin` como smoke largo para roturas estructurales

Orden recomendado de aceleración:

1. fetch/render visible del `VIC-I`
2. si hace falta después, partes calientes del `VIA6522`
3. dejar audio y lógica de control en Python en este primer corte

## Verificación más reciente

- `./.venv/bin/python -m pytest -q tests/test_via6522.py`
  - `32 passed`
- `./.venv/bin/python -m pytest -q tests/test_cli.py tests/test_machine_families.py tests/test_keymaps.py tests/test_via6522.py tests/test_vic20.py`
  - `117 passed`
- `./.venv/bin/python -m pytest -q tests/test_m6502.py tests/test_kim1.py`
  - `60 passed`

## Comandos útiles

- smoke `VIC-20 NTSC`:
  - `multiemu run vic20ntsc --frontend pygame --rom basic=roms/basic.901486-01.bin --rom kernal=roms/kernal.901486-07.bin --rom char=roms/characters.901460-03.bin`
- smoke con `Spider City`:
  - `multiemu run vic20ntsc --frontend pygame --rom basic=roms/basic.901486-01.bin --rom kernal=roms/kernal.901486-07.bin --rom char=roms/characters.901460-03.bin --rom cart=roms/Spider\\ City.NTSC.prg`
- smoke con diagnóstico:
  - `multiemu run vic20ntsc --frontend pygame --rom basic=roms/basic.901486-01.bin --rom kernal=roms/kernal.901486-07.bin --rom char=roms/characters.901460-03.bin --rom cart=roms/diag-vic20.bin`

## Reentrada recomendada

La próxima sesión debería empezar así:

1. abrir [vic20.py](/home/tobias/dev/multiemu/machines/m6502/vic20.py) y
   [vic6560.py](/home/tobias/dev/multiemu/chipsets/vic6560.py)
2. preparar `vic6560_accel.pyx` como primer acelerador selectivo
3. mantener la implementación Python como referencia semántica
4. verificar contra:
   - `tests/test_vic20.py`
   - `tests/test_via6522.py`
   - `Spider City.NTSC.prg`
   - `diag-vic20.bin` como smoke largo
