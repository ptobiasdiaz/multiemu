Aqui tienes un contexto de reentrada breve y actualizado del proyecto.

---

# Proyecto

`MultiEmu` es un multiemulador de maquinas retro en Python + Cython.

Direccion actual:

- CPU y dispositivos calientes en Cython
- maquina, cableado e integracion en Python
- frontends desacoplados
- ruta principal de video y streaming basada en `rgb24`

Version de trabajo actual:

- `0.0.2`

---

# Estado general

Familias visibles ahora:

- `spectrum16k`
- `spectrum48k`
- `cpc464`

La arquitectura que se esta consolidando es:

- implementacion acelerada en `devices/*_accel.pyx`
- wrappers de produccion minimos en `devices/*.py`
- referencias Python movidas a `tests/fallbacks/` solo para equivalencia y tests

El contrato de video de produccion ya no es el framebuffer estructurado.

La salida canonica es:

- `framebuffer_rgb24`

La limpieza de `framebuffer` en produccion ya esta hecha en Spectrum, CPC,
frontend local y runtime remoto.

---

# CPU Z80

La CPU Z80 en Cython arranca ROMs reales de Spectrum y CPC.

Punto importante reciente:

- se corrigio `run_cycles()` para que el reloj siga avanzando en `HALT`

Ese bug hacia que ciertas cargas, especialmente ROMs de prueba del CPC basadas
en `HALT` + interrupciones, corriesen demasiado rapido.

Hay regresion especifica en:

- `tests/test_z80_core.py`

---

# Maquinas

## Spectrum

Archivos principales:

- `machines/z80/spectrum.py`
- `machines/z80/spectrum48k.py` como shim de compatibilidad
- `devices/ula.py`
- `devices/ula_accel.pyx`

Estado actual:

- `SpectrumBase`, `Spectrum16K` y `Spectrum48K` son la jerarquia vigente
- la ULA de produccion genera `rgb24` directamente
- `SpectrumBase` expone `frame_width` y `frame_height` desde la ULA
- teclado, beeper y puerto `0xFE` siguen en la maquina

La referencia Python de la ULA ya no forma parte de la ruta principal y vive en:

- `tests/fallbacks/ula_reference.py`

## CPC464

Archivo principal:

- `machines/z80/cpc.py`

Arquitectura actual:

- `CPC464` orquesta la maquina en Python
- chips y subsistemas principales del CPC ya tienen implementacion acelerada
- los nombres se acercan al hardware real

Chips/subsistemas actuales:

- `devices/cpc_gate_array.py` -> `CPCGateArray`
- `devices/cpc_crtc.py` -> `HD6845`
- `devices/cpc_ppi.py` -> `Intel8255`
- `devices/cpc_video.py` -> `CPCVideo`
- `devices/ay38912.py` -> `AY38912`

Implementaciones aceleradas correspondientes:

- `devices/cpc_gate_array_accel.pyx`
- `devices/cpc_crtc_accel.pyx`
- `devices/cpc_ppi_accel.pyx`
- `devices/cpc_video_accel.pyx`
- `devices/cpc_render_accel.pyx`
- `devices/ay38912_accel.pyx`

Estado funcional del CPC:

- ROM baja y ROM alta soportadas
- overlay de ROM sobre RAM
- Gate Array, CRTC y PPI cableados
- teclado CPC por matriz via PPI + PSG
- video principal en `rgb24`
- frontend local y TCP funcionando con CPC

Lo que todavia no se considera cerrado:

- fidelidad fina de video
- fidelidad del `AY-3-8912`
- teclado CPC en pulsaciones rapidas
- perifericos como cassette

Las referencias Python del CPC viven ahora en:

- `tests/fallbacks/cpc_chip_references.py`
- `tests/fallbacks/cpc_render_reference.py`
- `tests/fallbacks/cpc_video_reference.py`

---

# Video

Regla actual de arquitectura:

- produccion consume y entrega `rgb24`
- helpers de framebuffer estructurado, si existen, pertenecen a referencias o tests

Impacto ya aplicado:

- Spectrum produce `rgb24`
- CPC produce `rgb24`
- `frontend/pygame_frontend.py` consume `rgb24`
- `multiemu/remote_runtime.py` codifica y envia `rgb24`

Esto simplifica la ruta normal y evita conversiones por frame que ya no aportan
valor en produccion.

---

# Audio

## Spectrum

- beeper clasico del puerto `0xFE`

## CPC

- PSG basado en `AY-3-8912`
- integracion CPC via `Intel8255`

Estado practico del `AY38912`:

- registros, tonos, ruido, envolvente y puertos estan implementados
- existe ruta accel + referencia
- es suficiente para seguir con CPC
- todavia no se da por fidelidad completa

Archivos clave:

- `devices/ay38912.py`
- `devices/ay38912_accel.pyx`
- `tests/fallbacks/ay38912_reference.py`
- `tests/test_ay38912.py`

Se generaron ROMs de prueba de sonido para CPC en:

- `tools/build_cpc_sound_test_rom.py`
- `roms/generated/cpc_ode_to_joy.rom`

Sirvieron para descubrir el bug de timing del Z80 en `HALT`, pero la calidad
musical del CPC todavia no se considera buena.

---

# Frontends y runtimes

Frontends/runtimes actuales:

- `frontend/pygame_frontend.py`
- `frontend/tcp_frontend.py`
- `frontend/tcp_pygame_client.py`
- `multiemu/remote_runtime.py`

Estado actual:

- `pygame` local funcionando
- cliente TCP `pygame` funcionando
- handshake remoto corregido para no depender de dimensiones `None`
- video y audio remotos siguen siendo funcionales, aunque el audio TCP no es la
  parte mas refinada del proyecto

CLI actual:

- `multiemu list-machines`
- `multiemu run`
- `multiemu serve`
- `multiemu connect`

---

# Tests

La suite ya no se basa en scripts manuales de arranque. Ahora el objetivo es
que los tests reales sean `pytest`.

Archivos principales de tests:

- `tests/test_spectrum.py`
- `tests/test_cpc464.py`
- `tests/test_ay38912.py`
- `tests/test_z80_bus.py`
- `tests/test_z80_core.py`
- `tests/test_accel_equivalence.py`
- `tests/test_cli.py`
- `tests/test_display_profiles.py`
- `tests/test_keymaps.py`

Las referencias Python para comparar con las implementaciones aceleradas viven
en:

- `tests/fallbacks/`

Decision importante:

- el fallback ya no es parte de la ejecucion normal del emulador
- su funcion ahora es validar semantica, servir de referencia y facilitar tests

---

# Decisiones de diseno

Estas notas no describen el estado puntual del codigo, sino decisiones de
arquitectura que conviene preservar entre sesiones.

## CLI y registros

La CLI publica vive en:

- `multiemu/cli.py`

La idea sigue siendo:

- no usar `tests/` como punto de entrada del emulador
- mantener un CLI estable para uso manual y automatizaciones
- dejar la logica de seleccion en registros/factorias, no en `if/elif`

Registros relevantes:

- `multiemu/machine_registry.py`
- `multiemu/runtime_registry.py`

Separacion actual de runtimes:

- `LOCAL_FRONTENDS`
- `SERVER_TRANSPORTS`
- `CONNECT_TRANSPORTS`
- `CONNECT_FRONTENDS`

Decision importante:

- `connect` separa transporte y frontend
- no conviene colapsar eso en ids artificiales como `tcp-pygame`

## Politica de busqueda de ROMs

La busqueda de ROMs no debe depender del arbol del repositorio.

Si no se pasa `--rom`, cada slot busca en este orden:

1. `CWD`
2. `$HOME/.local/share/multiemu/`
3. `/usr/local/share/multiemu/roms/`
4. `/usr/share/multiemu/`

Slots/nombres por defecto vigentes:

- `spectrum16k` -> `spec16k.rom`
- `spectrum48k` -> `spec48k.rom`
- `cpc464` slot `os` -> `OS_464.ROM`

Para CPC se mantiene el modelo de slots nombrados, no una proliferacion de
flags tipo `--rom2`, `--rom3`.

## Perfiles de display

Los perfiles de display viven en:

- `video/display_profiles.py`

Su funcion es separar:

- el raster/hardware que produce la maquina
- la ventana visible o perfil presentado al usuario

Esto se comparte entre Spectrum y CPC, y debe seguir asi.

## Runtime remoto

La base comun del frontend remoto vive en:

- `multiemu/remote_runtime.py`

Clase principal:

- `RemoteFrontendSession`

La intencion sigue siendo que la sesion remota comun concentre:

- loop de emulacion remoto
- merge de input por frame
- ritmo/cadencia
- codificacion de video
- drenado de audio

Y que el transporte concreto, hoy TCP, se encargue sobre todo de:

- sockets
- parsing de mensajes
- colas/salida

## Convencion de documentacion

La documentacion interna debe preservar decisiones, no narrar el codigo.

Regla acordada:

- docstrings de modulo o clase cuando aporten contexto arquitectonico
- comentarios breves solo para decisiones no obvias o rarezas de hardware
- evitar comentarios redundantes que solo repitan el codigo

---

# Prioridades abiertas

Si se retoma el trabajo del CPC, el orden recomendado es:

1. fidelidad basica de video e input
2. afinar `AY38912`
3. medir rendimiento real del CPC completo
4. decidir si merece la pena mas Cython o mas hardware

Si aparece un bug de timing raro en CPC, recordar primero:

- revisar relacion entre `run_frame()`, interrupciones y `HALT`
- comprobar si la ROM o test depende de esperas por frame
