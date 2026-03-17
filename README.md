# MultiEmu

`MultiEmu` es un multiemulador de máquinas retro escrito en Python y Cython.

La intención del proyecto es separar con claridad:

- CPU y partes críticas de rendimiento
- definición de máquinas y hardware
- frontends locales y remotos
- transporte y presentación en el CLI

El foco actual del repositorio está en la familia ZX Spectrum sobre Z80, pero
la estructura está pensada para crecer hacia más máquinas y más frontends sin
mezclar toda la lógica en un único punto de entrada.

## Estado actual

Máquinas soportadas hoy:

- `spectrum16k`
- `spectrum48k`

Frontends y transportes disponibles hoy:

- `run --frontend pygame`
- `serve --transport tcp`
- `connect --transport tcp --frontend pygame`

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

Si no pasas `--rom`, `multiemu` buscará automáticamente la ROM requerida en
este orden:

1. directorio actual
2. `$HOME/.local/share/multiemu/`
3. `/usr/local/share/multiemu/roms/`
4. `/usr/share/multiemu/`

Nombres esperados por defecto:

- `spectrum16k` -> `spec16k.rom`
- `spectrum48k` -> `spec48k.rom`

También puedes pasar una ruta explícita con `--rom`.

## Ver máquinas disponibles

```bash
multiemu list-machines
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
