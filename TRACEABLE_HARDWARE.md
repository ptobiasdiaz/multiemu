# Hardware trazable

Este documento define el contrato minimo que debe cumplir cualquier CPU, chip,
bus, memoria o periferico nuevo para ser usable desde el modo debug remoto.

No es una guia de implementacion del frontend. Es una guia de modelado del
hardware para que pueda:

- inspeccionarse
- pausarse
- modificarse
- reanudarse

sin introducir acoplamiento ad hoc con un depurador concreto.

## Objetivo

Todo hardware nuevo debe poder exponer y restaurar su estado de forma
estructurada y serializable a JSON.

El contrato base es:

- `read_state() -> dict`
- `write_state(state: dict) -> None`

## Reglas generales

### 1. Estado JSON estable

`read_state()` debe devolver un `dict` JSON-serializable.

Reglas:

- claves estables y legibles
- valores escalares para registros, flags y contadores
- arrays de enteros para memoria o buffers binarios
- `__meta__` opcional para tipo o metadatos utiles

Ejemplo:

```python
{
    "__meta__": {"type": "VIA6522"},
    "ifr": 0x40,
    "ier": 0x60,
    "t1_counter": 0x1234,
}
```

### 2. `write_state()` debe restaurar el mismo modelo

`write_state()` debe consumir el mismo formato devuelto por `read_state()`.

Reglas:

- no asumir objetos Python externos
- no depender de callbacks o wiring vivo dentro del estado serializado
- restaurar registros y latches internos necesarios para continuar la emulacion
- recalcular lineas derivadas si hace falta
  - por ejemplo IRQ/NMI, flags agregados, caches internas

### 3. No serializar referencias vivas

No deben entrar en el estado:

- callbacks
- sockets
- ficheros
- punteros a frontend
- referencias a otras maquinas
- objetos no serializables

Si un objeto necesita wiring externo, ese wiring pertenece a la construccion de
la maquina, no al blob de estado.

### 4. Memoria como arrays de bytes

Para RAM, VRAM, OAM, HRAM, color RAM, etc.:

- exponer arrays de enteros `0..255`
- mantener el nombre del bloque explicito

Ejemplo:

```python
{
    "__meta__": {"type": "RAMBlock"},
    "size": 8192,
    "writable": True,
    "data": [0, 1, 2, 3]
}
```

### 5. Mantener separados estado y descubrimiento

El objeto hardware expone su estado.

La maquina expone el descubrimiento de hardware con `debug_devices()`.

Eso evita:

- depender de introspeccion accidental
- ids inestables
- acoplar el depurador a nombres de atributos no publicos

## Contrato de maquina para debug

Las maquinas deben exponer ids estables para debug mediante:

```python
def debug_devices(self) -> list[dict]:
    return [
        self._debug_device("machine", self, "machine", label="Machine"),
        self._debug_device("cpu", self.cpu, "cpu", label="CPU"),
        self._debug_device("bus", self.bus, "bus", label="Bus"),
    ]
```

Cada descriptor debe contener:

- `id`
- `obj`
- `kind`
- `label`
- `writable`

## Convenciones de `device_id`

Reglas:

- ids cortos, estables y semanticos
- no depender de `repr()`
- no usar rutas de modulo como id primario salvo ausencia total de alternativa

Buenos ejemplos:

- `cpu`
- `bus`
- `ppu`
- `apu`
- `dma`
- `vic`
- `via1`
- `via2`
- `ula`
- `crtc`
- `psg`
- `ram`
- `rom`
- `color_ram`

## Qué estado incluir

### CPUs

Incluir al menos:

- registros visibles
- PC/SP
- flags
- estado de interrupciones
- halted/stopped
- latches internos necesarios para reanudar correctamente

### Buses

Incluir:

- flags de IRQ/NMI/IE equivalentes si son parte del bus
- bancos seleccionados
- memorias internas propias
- metadatos minimos del mapa si son utiles para debug

No incluir:

- handlers Python
- wiring de callbacks

### Chips de video/audio/IO

Incluir:

- registros MMIO
- contadores de raster o timing
- latches de fetch
- FIFOs o buffers internos si afectan a la continuacion fiel
- lineas de control si son parte del estado observable

### Perifericos

Incluir:

- estado de control
- posicion o punteros internos si afectan a emulacion
- buffers si son parte del estado emulado

## Qué hacer cuando una clase Cython no permite `setattr`

Muchas clases Cython con `cdef` no exponen atributos Python-settable.

En esos casos:

- no usar helper generico basado en `setattr`
- implementar `read_state()` / `write_state()` manualmente

Esto aplica especialmente a:

- cores de CPU
- bloques de memoria con campos `cdef`
- clases con buffers o punteros

## Regla para nuevo hardware

Toda arquitectura nueva o maquina nueva debe nacer con:

1. ids estables en `debug_devices()`
2. `read_state()` / `write_state()` en CPU y bus
3. `read_state()` / `write_state()` en los chips internos principales
4. tests de roundtrip al menos para:
   - CPU
   - bus
   - un chip principal

No debe dejarse para “mas adelante” como deuda implicita.

## Cobertura minima recomendada por maquina nueva

Checklist:

- `cpu.read_state()/write_state()`
- `bus.read_state()/write_state()`
- RAM principal serializable
- video chip serializable
- audio chip serializable si existe
- `machine.debug_devices()` con ids estables
- test de roundtrip de maquina o sesion debug

## Trabajo pendiente conocido

Pendientes del arbol actual:

- ampliar `read_state()` / `write_state()` a mas chips grandes
  - `PPU/APU` de Game Boy
  - `ULA`
  - `AY`
  - otros chips de CPC/Spectrum
- exponer una API HTTP/REST opcional por encima del mismo `DebugSession`

