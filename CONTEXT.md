`CONTEXT.md` es un documento estable de decisiones tecnicas y arquitecturales.

No debe usarse como diario de sesion, changelog, roadmap ni snapshot temporal
del estado del codigo. Para eso existe `NEXT_SESSION.md` y, a nivel de
proyecto, `TODO.md`.

Si una decision cambia, este fichero debe actualizarse con:

- la nueva decision
- la decision anterior que sustituye
- el motivo del cambio

---

# Principios del proyecto

## Separacion de responsabilidades

`MultiEmu` sigue estas reglas:

- la maquina y el cableado entre chips viven en Python
- los chips o rutas calientes pueden vivir en Cython
- los frontends y transportes deben mantenerse desacoplados de la logica de
  maquina
- las referencias Python de semantica deben vivir en `tests/fallbacks/` cuando
  sirvan para validar implementaciones aceleradas

Esta separacion es deliberada. El objetivo no es maximizar Cython por defecto,
sino mantener visible la arquitectura de cada maquina.

## Contrato de produccion para video

La salida canonica de video en produccion es:

- `framebuffer_rgb24`

Decision vigente:

- la ruta de produccion consume y entrega `rgb24`
- representaciones estructuradas o auxiliares de framebuffer pertenecen a
  referencias, utilidades o tests, no a la ruta principal

Motivo:

- simplifica frontends y runtime remoto
- evita conversiones por frame sin valor arquitectonico
- unifica Spectrum, CPC, Game Boy y futuras maquinas bajo el mismo contrato

## Frontends y runtime remoto

La sesion remota comun debe concentrar:

- loop remoto
- merge de input por frame
- ritmo/cadencia
- codificacion de video
- drenado de audio

Los transportes concretos deben limitarse a:

- sockets o medio de transporte
- parsing de mensajes
- colas de entrada/salida

Decision vigente:

- no acoplar transporte y frontend en un identificador unico artificial
- mantener la separacion `transport` / `frontend` en la CLI y en los registros

## Politica de documentacion interna

La documentacion interna debe preservar decisiones y restricciones, no narrar
paso a paso el codigo actual.

Reglas:

- usar docstrings para contexto arquitectonico o de hardware
- usar comentarios breves para decisiones no obvias
- evitar comentarios redundantes que solo repitan el codigo
- mantener `CONTEXT.md` como documento de decisiones duraderas
- mantener `NEXT_SESSION.md` como documento tactico de continuacion

---

# Estructura del codigo

## Familias de CPU

Las familias de CPU deben vivir separadas cuando la semantica real difiera de
forma importante.

Decision vigente:

- `Z80`, `LR35902` y `m6502` deben tener implementaciones separadas
- solo se comparte infraestructura realmente neutra
- no se debe forzar una jerarquia comun artificial de CPUs "parecidas"

Motivo:

- reduce acoplamiento falso
- evita contaminar una familia con detalles de otra
- facilita evolucion independiente de decoder, flags, timings e interrupciones

## Bases de maquina

La infraestructura comun de maquinas debe ser minima y neutral.

Decision vigente:

- las utilidades de ciclo de vida, audio, framebuffer e input pueden vivir en
  bases compartidas
- las bases especificas de familia (`Z80`, `LR35902`, `m6502`) deben quedarse
  en su namespace
- no introducir abstracciones globales nuevas en `BaseMachine` si no hay un
  patron claro compartido por varias familias reales

## Runners de frame

Los runners compartidos son la abstraccion comun permitida para el avance por
frame.

Decisiones vigentes:

- `SteppedFrameRunner` para maquinas orientadas a pasos de CPU
- `ScanlineFrameRunner` para maquinas orientadas a scanline
- el frame loop comun puede vivir en Python y/o Cython, pero la orquestacion
  de maquina debe seguir siendo visible en Python

## Organizacion de chipsets y perifericos

Decision vigente:

- `devices/` debe reservarse para perifericos y medios externos
  - cintas
  - discos
  - FDCs
  - cartuchos y soportes similares
- `chipsets/` debe agrupar chips y subsistemas internos de maquina
  - ULA
  - AY-3-8912
  - Gate Array
  - CRTC
  - PPI
  - componentes internos equivalentes

Motivo:

- separar mejor hardware interno de medios/perifericos
- hacer la arquitectura de cada maquina mas legible
- preparar el arbol para crecer sin convertir `devices/` en un cajon de sastre

Estado de la decision:

- aprobada
- completada para los chipsets y aceleradores de primer nivel
- `devices/` queda como espacio de perifericos y medios
- `chipsets/` queda como espacio canonico para chips internos y aceleradores
- evitar mezclar futuras migraciones de arbol con cambios funcionales no
  relacionados cuando sea posible

## Game Boy

Decision vigente:

- el namespace `devices/gameboy/` se usa hoy como agrupacion funcional del
  hardware de la maquina
- si en el futuro se decide converger hacia `chipsets/`, debe hacerse como
  refactor separado y explicito, no mezclado con cambios de comportamiento

Motivo:

- reducir riesgo en una maquina que ya tiene bastante superficie funcional
- evitar una migracion demasiado grande en una sola release

---

# CLI, registros y ROMs

## Registro de maquinas

La seleccion de maquinas no debe vivir en cascadas de `if/elif` dentro de la
CLI.

Decision vigente:

- la CLI publica vive en `multiemu/cli.py`
- la descripcion declarativa de maquinas vive en `multiemu/machine_registry.py`
- la seleccion de runtimes y transportes vive en registros dedicados

Motivo:

- mantener la CLI estable
- reutilizar la misma logica desde `run`, `serve`, `connect` y futuros entry
  points
- hacer extensible la incorporacion de nuevas maquinas

## Politica de slots de ROM

Las maquinas deben exponerse mediante slots nombrados.

Decisiones vigentes:

- no proliferar flags especificos tipo `--rom2`, `--rom3`
- en maquinas con un solo slot principal se puede aceptar forma corta
- en maquinas con varios slots, el uso preferente es `--rom slot=fichero`
- si un slot no tiene nombres por defecto, debe exigirse explicitamente

Motivo:

- mantener una interfaz consistente para maquinas heterogeneas
- evitar reglas especiales por maquina

## Politica de busqueda de ROMs

La busqueda de ROMs no debe depender del arbol del repositorio.

Orden vigente:

1. `CWD`
2. `$HOME/.local/share/multiemu/`
3. `/usr/local/share/multiemu/roms/`
4. `/usr/share/multiemu/`

Motivo:

- alinear desarrollo local e instalacion real
- evitar dependencias implicitas del checkout

## Cintas y discos

Decision vigente:

- los medios deben entrar como slots opcionales declarativos
- el frontend puede exponer controles comunes como `play/pause`, pero el
  comportamiento del medio debe quedarse en el dispositivo correspondiente
- no deformar silenciosamente la señal de cinta para "hacer que cargue"
- si se quiere acelerar carga, debe ser por una via explicita de control o modo
  turbo

---

# Politica de implementacion acelerada

## Relacion entre Python y Cython

Decision vigente:

- la implementacion acelerada puede ser la canonica del paquete productivo
- cuando exista una ruta Cython canonica, la referencia Python debe moverse a
  `tests/fallbacks/`
- la implementacion Python y la acelerada deben mantenerse semanticamente
  alineadas
- no debe introducirse funcionalidad en Cython sin referencia equivalente o sin
  tests que fijen la semantica

Motivo:

- reducir deuda de divergencia
- permitir depuracion y comparacion reproducible

## Referencias en tests

Decision vigente:

- las referencias Python para comparar con implementaciones aceleradas viven en
  `tests/fallbacks/`
- esas referencias no son la ruta normal de ejecucion del emulador
- su objetivo es validar semantica y servir de modelo de regresion

Aplicacion vigente:

- `m6502` sigue ya esta politica
- las pruebas de equivalencia deben comparar el core productivo frente a la
  referencia Python cargada desde `tests/fallbacks/`

## Regla para cambios de decoder o hardware caliente

Al ampliar un core o chipset caliente:

- fijar primero la semantica observable
- añadir o ajustar tests
- mantener alineadas las variantes Python/Cython cuando existan ambas

Esta regla es especialmente importante en:

- `Z80`
- `LR35902`
- render y chips acelerados del CPC

---

# Decisiones por maquina

## Spectrum

Decisiones vigentes:

- `SpectrumBase`, `Spectrum16K` y `Spectrum48K` son la jerarquia valida
- teclado, beeper y puerto `0xFE` siguen en la maquina
- la ULA produce `rgb24` directamente
- el soporte de cinta se modela como señal `EAR` observable por ROM

Sobre formatos de cinta:

- `TZX` y `TAP` son formatos aceptables para Spectrum
- la pausa inicial y el control manual de cinta son parte del flujo esperado
- el frontend `pygame` usa `F1` para `play/pause`

## CPC464

Decisiones vigentes:

- `CPC464` sigue siendo una maquina cableada en Python
- Gate Array, CRTC, PPI, video y PSG son subsistemas separados
- la RAM sigue estando fisicamente presente incluso bajo ROM
- la ROM alta debe tratarse como banco seleccionable, no como un caso especial
  ad hoc

Sobre medios:

- el cassette CPC acepta `CDT/TZX`
- el disco CPC acepta `DSK`
- el soporte de disco puede crecer de forma incremental desde un FDC minimo

Sobre fidelidad:

- prioridad en CPC: coherencia funcional antes que exactitud de timing total
- cualquier mejora fina de video o AY debe preservar la legibilidad de la
  orquestacion en Python

## KIM-1 y m6502

Decisiones vigentes:

- `m6502` crece como familia propia
- `KIM-1` se usa como primera maquina real para validar esa familia
- el core productivo de `m6502` es la ruta Cython; la referencia Python vive en
  `tests/fallbacks/`
- las ROMs de `KIM-1` deben pasarse por slots explicitos, no hardcodearse por
  nombre dentro de la maquina
- el display y keypad deben modelarse a traves del `6530`, no mediante MMIO
  inventado ajeno al monitor
- la validez del soporte `KIM-1` debe fijarse con ROMs originales del monitor,
  no solo con ROMs sinteticas
- la entrada/salida TTY debe modelarse como linea serie bit-bang en el `6530`
  y validarse con rutas reales del monitor
- las rutas reales del monitor que se consideran criterio de verdad incluyen al
  menos:
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

Motivo:

- usar software real del monitor como criterio de verdad
- validar arquitectura antes de saltar a maquinas 6502 mas grandes

## Game Boy

Decisiones vigentes:

- `LR35902` no es una variante refactorizada del `Z80`
- `DMG` se modela como maquina propia
- cartucho, PPU, APU, timer, DMA, joypad e interrupciones son subsistemas
  separados
- la salida de video de produccion debe seguir siendo `rgb24`

Si en algun momento cambia la estrategia de organizacion interna de estos
componentes, debe documentarse aqui como cambio de decision, no solo como
movimiento de ficheros.

---

# Politica de cambios futuros

Antes de introducir una nueva abstraccion o refactor grande, comprobar:

- si resuelve un patron real en varias maquinas
- si mejora claridad arquitectonica y no solo simetria estetica
- si separa mejor hardware interno, perifericos y frontends
- si mantiene visible la maquina en Python

Si una decision de este documento deja de ser valida:

- no se borra sin mas
- se sustituye por la nueva decision
- se deja constancia breve del motivo del cambio
