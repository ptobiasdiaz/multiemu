Aquí tienes el contexto actualizado del proyecto para retomarlo en otra sesión sin perder decisiones importantes.

---

# Proyecto

`MultiEmu` es un multiemulador de máquinas retro en **Python + Cython**.

Filosofía actual:

- CPU en Cython para rendimiento
- máquinas y hardware en Python para flexibilidad
- frontends desacoplados
- arquitectura pensada para soportar varias máquinas con la misma CPU

La CPU actual es **Z80** y la familia activa es **ZX Spectrum**.

---

# Estado actual

## CPU Z80

La CPU ya ejecuta suficiente del set de instrucciones para arrancar ROMs del Spectrum.

Durante el desarrollo se añadieron, entre otras:

- `LD A,(DE)`
- `LD (DE),A`
- `EX (SP),HL`
- `LD SP,HL`
- opcodes prefijados `ED`
- `IN r,(C)`
- `OUT (C),r`
- block instructions como `LDIR`, `CPIR`, `INIR`, `OTIR`

La ROM del Spectrum 48K arranca.

---

# Máquinas

## Jerarquía actual

La familia Spectrum ya no está implementada como una única clase aislada.

Ahora existe:

- `machines/z80/spectrum.py`
  - `SpectrumBase`
  - `Spectrum16K`
  - `Spectrum48K`

Además se mantiene:

- `machines/z80/spectrum48k.py`

como shim de compatibilidad para imports antiguos.

## Diseño de `SpectrumBase`

`SpectrumBase` concentra lo común a la familia Spectrum:

- ULA
- beeper
- teclado
- puerto `0xFE`
- render de vídeo
- frame loop
- audio
- helpers de RAM/ROM

Los modelos concretos especializan principalmente:

- tamaño de RAM
- rango de RAM mapeado
- semántica visible desde helpers como `peek`, `poke`, `load_ram`

## Spectrum16K

`Spectrum16K` existe ya como máquina independiente.

Características actuales:

- ROM en `0x0000-0x3FFF`
- RAM real en `0x4000-0x7FFF`
- zona alta no mapeada a partir de `0x8000`
- `peek()` en RAM no mapeada devuelve `0xFF`
- `poke()` y `load_ram()` fuera de la RAM real lanzan `ValueError`

## Spectrum48K

`Spectrum48K` ahora hereda de `SpectrumBase`.

Características actuales:

- ROM en `0x0000-0x3FFF`
- RAM en `0x4000-0xFFFF`

## Verificación hecha

Se comprobó:

- `tests/test_spectrum16k.py`
- `tests/test_spectrum_ram_exec.py`

y la jerarquía exporta correctamente:

- `SpectrumBase`
- `Spectrum16K`
- `Spectrum48K`

---

# Vídeo

La ULA actual sigue renderizando el framebuffer leyendo la RAM del Spectrum.

Memoria de pantalla:

- bitmap `0x4000`
- attributes `0x5800`

Resolución visible:

- `256x192`

Frame completo con borde:

- `352x296`

Limitaciones actuales:

- sin contención
- sin timing por scanline
- sin borde por ciclo

La imagen se ve correctamente.

---

# Teclado

El teclado del Spectrum sigue modelado como matriz de 8 filas.

Puerto:

- `0xFE`

La máquina mantiene:

- `keyboard_rows[8]`

El frontend local y el frontend TCP envían eventos/estados sobre esa matriz.

---

# Audio

## Generación

El audio sigue saliendo del beeper conectado al puerto `0xFE`, bit 4.

La ULA contiene:

- `ULABeeper`

La síntesis sigue siendo PCM `16-bit` mono a `44100 Hz`, con unas `~882` muestras por frame.

## Frontend local

`frontend/pygame_frontend.py` se mejoró durante esta sesión.

Cambio importante:

- ya no alimenta `pygame.mixer` con chunks muy pequeños
- acumula audio y lo reproduce en bloques más largos (`>= 2048` muestras)
- el buffer del mixer se inicializa con ese tamaño

Resultado:

- el audio local es mucho más limpio
- todavía puede haber algunos `pocs`, pero bastante menos desagradables

## Frontend TCP

Existe:

- `frontend/tcp_frontend.py`
- `frontend/tcp_pygame_client.py`

Estado actual:

- handshake `hello/welcome`
- varios clientes simultáneos
- `input_state` compartido para `keyboard_0`
- fusión del teclado por frame
- vídeo y audio enviados por TCP

Mejoras hechas:

- el servidor ya no trata audio y vídeo como un único payload descartable
- el vídeo mantiene solo el frame más reciente por cliente
- el audio se acumula aparte por cliente
- el cliente TCP usa chunks de reproducción más largos, igual que el frontend local

Estado del audio TCP:

- ha mejorado mucho
- sigue siendo peor que el frontend local
- todavía hay ruido/jitter residual

Se dejó un `FIXME` en:

- `frontend/tcp_pygame_client.py`

Motivo:

- el audio TCP sigue acoplado al framing/ritmo de entrega del vídeo
- a futuro conviene separar el camino lógico de audio del de vídeo

---

# Frontends

## Local

- `frontend/pygame_frontend.py`

## Remoto

- `frontend/tcp_frontend.py`
- `frontend/tcp_pygame_client.py`

## Backend adaptador

Existe un adaptador compartido:

- `frontend/backend.py`

`LocalMachineBackend` expone el estado de máquina al frontend y ahora también delega `frame_counter`.

---

# Estructura del repo

Se hicieron cambios de limpieza para una pre-release:

- añadido `README.md`
- añadida licencia `MIT` en `LICENSE`
- añadido `.gitignore` en la raíz
- actualizados metadatos en `pyproject.toml`
- versión actual marcada como `0.1.0a1`

## Scripts y tests

Todos los `test_*` se movieron a:

- `tests/`

---

# Decisiones nuevas de esta sesión

## CLI unificado

Ahora existe una capa de CLI propia para el proyecto en:

- `multiemu/cli.py`

El comando instalado es:

- `multiemu`

Objetivo de diseño:

- dejar de usar los `tests/test_*.py` como punto de entrada principal
- exponer una interfaz estable para usuarios y futuras automatizaciones
- mantener el parser fino y mover la lógica real a registros/factorías

Comandos actuales:

- `multiemu list-machines`
- `multiemu run`
- `multiemu serve`
- `multiemu connect`
- `multiemu client`

Notas:

- `client` es alias de `connect`
- `run` usa `--frontend`
- `serve` usa `--transport`
- `connect` usa `--transport` y `--frontend`

Defaults actuales:

- frontend local por defecto: `pygame`
- transporte remoto por defecto: `tcp`
- frontend de conexión por defecto: `pygame`

## Registro de máquinas

Existe un registro central en:

- `multiemu/machine_registry.py`

Propósito:

- resolver máquinas soportadas desde un punto único
- separar creación de máquinas del parser CLI
- facilitar añadir nuevas familias o modelos sin meter `if/elif` en el CLI

La construcción pública actual es:

- `instantiate_machine(machine_id, rom_path=None)`

Comportamiento importante:

- la factoría resetea siempre la máquina tras construirla
- esto garantiza un estado inicial homogéneo para `run` y `serve`

## Política de búsqueda de ROMs

Si no se pasa `--rom`, cada máquina busca un nombre de ROM canónico en este orden:

1. `CWD`
2. `$HOME/.local/share/multiemu/`
3. `/usr/local/share/multiemu/roms/`
4. `/usr/share/multiemu/`

Nombres canónicos actuales:

- `spectrum16k` -> `spec16k.rom`
- `spectrum48k` -> `spec48k.rom`

Decisión de diseño:

- la búsqueda por defecto no depende del árbol del repositorio
- así el comportamiento es igual en desarrollo e instalación real

Si no aparece la ROM, el CLI falla con error claro y muestra el search path.

## Registro de runtimes

Existe una capa declarativa para seleccionar runtimes en:

- `multiemu/runtime_registry.py`

Objetivo:

- desacoplar selección de frontend/transporte del código del parser
- permitir crecimiento incremental sin reescribir handlers

Separación actual:

- `LOCAL_FRONTENDS`
- `SERVER_TRANSPORTS`
- `CONNECT_TRANSPORTS`
- `CONNECT_FRONTENDS`

Punto importante:

- en `connect`, transporte y frontend ya no se modelan como una sola opción combinada
- la composición actual válida es `tcp + pygame`
- se dejó así para que futuras combinaciones no obliguen a crear ids artificiales tipo `tcp-pygame`, `ws-pygame`, etc.

## Desacoplo del servidor remoto

Se extrajo una base común para sesiones remotas en:

- `multiemu/remote_runtime.py`

Clase principal:

- `RemoteFrontendSession`

Responsabilidades de esa capa:

- loop de emulación remoto
- cadence/frame budget
- merge de input por frame
- codificación base de framebuffer a `rgb24`
- drenado de audio del backend

Implementación concreta actual:

- `frontend/tcp_frontend.py`

`TcpFrontend` ya no contiene toda la semántica de sesión remota, sino sobre todo:

- aceptación de sockets
- gestión de clientes
- parsing de mensajes TCP
- cola/salida de payloads

Decisión de diseño:

- `serve` ya no está acoplado conceptualmente a TCP, aunque hoy TCP sea el único transporte implementado

## Ctrl-C en `serve`

El comando `multiemu serve` captura `KeyboardInterrupt`.

Comportamiento deseado:

- cierre limpio
- sin traceback al pulsar `Ctrl-C`
- mensaje operacional claro al usuario
- retorno `130`

La captura se hace en el handler del CLI, no en la capa global.

Motivo:

- la semántica especial aplica al servidor de larga duración y no necesariamente al resto de comandos

## Convención de documentación para futuras sesiones

Se acordó que los archivos tocados deben mantener contexto homogéneo mediante:

- docstrings de módulo cuando aporten contexto arquitectónico
- docstrings en funciones/clases públicas
- comentarios breves sólo donde expliquen decisiones no obvias

No se buscan comentarios redundantes, sino preservar decisiones de diseño para continuidad entre sesiones.

Ahora conviene ejecutarlos como módulos, por ejemplo:

- `python -m tests.test_spectrum_rom`
- `python -m tests.test_spectrum16k_rom`
- `python -m tests.test_server_spectrum48k`
- `python -m tests.test_client`

Hay además:

- `tests/test_server_pectrum48k.py`

como wrapper de compatibilidad para el nombre antiguo con typo.

Importante:

muchos de esos `test_*.py` no son tests formales, sino launchers o smoke tests.

La intención explícita para la próxima sesión es:

- crear una aplicación específica para instanciar y lanzar máquinas
- dejar `tests/` más orientado a tests reales

---

# ROMs y launchers relevantes

Actualmente se usan en scripts de arranque:

- `48E.rom` para Spectrum 48K
- `cl-48.rom` para Spectrum 16K

Launchers útiles:

- `tests/test_spectrum_rom.py`
- `tests/test_spectrum16k_rom.py`
- `tests/test_server_spectrum48k.py`
- `tests/test_client.py`

---

# Próximos pasos razonables

Prioridad natural para continuar:

1. Crear una app/CLI específica para instanciar máquinas y frontends
2. Separar launchers de tests reales
3. Seguir mejorando audio TCP desacoplando audio y vídeo
4. Seguir ampliando la familia Spectrum sobre `SpectrumBase`
5. Decidir cómo documentar/gestionar ROMs de usuario de cara a GitHub
