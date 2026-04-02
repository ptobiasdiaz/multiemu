# Protocolo de debug remoto

Este documento describe la extensión de protocolo disponible cuando la
emulación se ejecuta en modo debug mediante
[frontend/tcp_debug_frontend.py](/home/tobias/dev/multiemu/frontend/tcp_debug_frontend.py).

El objetivo es que un cliente externo pueda:

- pausar la emulación
- reanudarla
- avanzar instrucción a instrucción
- descubrir dispositivos depurables
- leer y escribir estado de máquina o dispositivo
- leer y escribir memoria

No describe una UI concreta. El cliente puede ser CLI, GUI o un adaptador HTTP.

## Handshake

El handshake base es el mismo que en el frontend TCP normal. La diferencia es
que el `welcome` anuncia capacidades de debug:

```json
{
  "type": "welcome",
  "debug": {
    "enabled": true,
    "features": [
      "pause",
      "resume",
      "step",
      "list_devices",
      "get_state",
      "set_state",
      "read_memory",
      "write_memory"
    ]
  }
}
```

Si `debug.enabled` es `false` o el bloque no existe, el servidor no garantiza
ninguno de los mensajes siguientes.

## Semántica de pausa

El frontend de debug usa un loop separado del loop rápido normal.

Consecuencia importante:

- la petición de pausa no se comprueba dentro del hot path del runtime normal
- una pausa pedida en mitad de un frame se hace efectiva en el límite de frame

Esto evita penalizar el rendimiento del modo no debug.

## Mensajes cliente -> servidor

### `debug.pause`

Solicita parar la ejecución.

```json
{"type":"debug.pause"}
```

Alias aceptado por compatibilidad:

```json
{"type":"pause"}
```

### `debug.resume`

Reanuda la ejecución si la máquina está parada.

```json
{"type":"debug.resume"}
```

Alias:

```json
{"type":"resume"}
```

### `debug.step`

Avanza una instrucción de CPU.

Requiere que la máquina esté pausada.

```json
{"type":"debug.step"}
```

Alias:

```json
{"type":"step"}
```

### `debug.list_devices`

Devuelve la lista de dispositivos depurables conocidos por la máquina.

```json
{"type":"debug.list_devices"}
```

Alias:

```json
{"type":"list_devices"}
```

### `debug.get_state`

Sin `device`, devuelve el estado completo de la máquina.

```json
{"type":"debug.get_state"}
```

Con `device`, devuelve solo el estado de ese dispositivo.

```json
{"type":"debug.get_state","device":"cpu"}
{"type":"debug.get_state","device":"ppu"}
{"type":"debug.get_state","device":"vic"}
```

Alias:

```json
{"type":"get_state"}
```

### `debug.set_state`

Escribe estado completo de máquina o de un dispositivo concreto.

```json
{"type":"debug.set_state","state":{"tstates":0},"ref":"r1"}
{"type":"debug.set_state","device":"cpu","state":{"PC":4096},"ref":"r2"}
```

Alias:

```json
{"type":"write_state","state":{...}}
```

### `debug.read_memory`

Lee una ventana de memoria desde el bus principal.

```json
{"type":"debug.read_memory","addr":4096,"count":32}
```

Alias:

```json
{"type":"read_memory","addr":4096,"count":32}
```

### `debug.write_memory`

Escribe bytes en memoria.

```json
{"type":"debug.write_memory","addr":4096,"data":[1,2,3],"ref":"r3"}
```

Alias:

```json
{"type":"write_memory","addr":4096,"data":[1,2,3]}
```

## Mensajes servidor -> cliente

### `paused`

Se emite cuando la pausa queda activa.

```json
{
  "type":"paused",
  "cpu": {...},
  "state": {...},
  "tstates": 1234,
  "frame_tstates": 456
}
```

### `resumed`

```json
{"type":"resumed"}
```

### `stepped`

Se emite tras ejecutar una instrucción en pausa.

```json
{
  "type":"stepped",
  "cpu": {...},
  "state": {...},
  "tstates": 1238,
  "frame_tstates": 460,
  "cycles": 4
}
```

### `state`

Estado completo de máquina cuando se pide `debug.get_state` sin `device`.

```json
{
  "type":"state",
  "cpu": {...},
  "state": {...},
  "tstates": 1234,
  "frame_tstates": 456,
  "frame_counter": 12
}
```

### `debug.state`

Estado de un dispositivo concreto.

```json
{
  "type":"debug.state",
  "device":"ppu",
  "state": {...}
}
```

### `debug.devices`

Inventario de dispositivos depurables.

```json
{
  "type":"debug.devices",
  "devices":[
    {"id":"machine","kind":"machine","label":"Machine","writable":true},
    {"id":"cpu","kind":"cpu","label":"CPU","writable":true},
    {"id":"bus","kind":"bus","label":"Bus","writable":true},
    {"id":"ppu","kind":"chip","label":"PPU","writable":true}
  ]
}
```

### `memory`

Respuesta a `debug.read_memory`.

```json
{
  "type":"memory",
  "addr":4096,
  "data":[0,1,2,3]
}
```

### `ack`

Confirmación de escritura de estado o memoria.

```json
{"type":"ack","ref":"r1"}
```

o, para `set_state`, incluyendo el estado resultante:

```json
{
  "type":"ack",
  "ref":"r2",
  "device":"cpu",
  "state":{"PC":4096}
}
```

### `error`

Errores de protocolo o de estado.

Ejemplos típicos:

- `handshake_required`
- `not_paused`
- `dispositivo de debug no soportado`
- `dispositivo de debug no escribible`

## Formato del estado

El payload de `state` y `debug.state` sigue el contrato definido en
[TRACEABLE_HARDWARE.md](/home/tobias/dev/multiemu/TRACEABLE_HARDWARE.md):

- `read_state() -> dict`
- `write_state(state: dict) -> None`

Reglas relevantes:

- claves estables y legibles
- enteros para registros, flags y contadores
- arrays de enteros para memoria o buffers binarios
- `__meta__` opcional para tipo y metadatos

Ejemplo:

```json
{
  "__meta__": {"type":"VIA6522"},
  "ifr": 64,
  "ier": 96,
  "t1_counter": 4660
}
```

Para memorias:

```json
{
  "__meta__": {"type":"RAMBlock"},
  "size": 8192,
  "data": [0, 1, 2, 3]
}
```

## Descubrimiento de dispositivos

Los ids estables se definen por máquina mediante `debug_devices()`.

Ejemplos comunes:

- `machine`
- `cpu`
- `bus`
- `ppu`
- `apu`
- `dma`
- `interrupts`
- `vic`
- `via1`
- `via2`
- `ula`
- `crtc`
- `psg`
- `ram`
- `rom`
- `cartridge`

Un cliente externo no debe deducir ids a partir de nombres de atributos Python.
Debe usar `debug.list_devices`.

## Alcance actual

La extensión de protocolo está pensada para el transporte TCP actual. La API
HTTP/REST se considera un adaptador futuro encima del mismo modelo de
`DebugSession`, no una segunda fuente de verdad.
