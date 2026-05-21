# Project Harness

Este documento define las reglas de ingeniería de `multiemu`.

Su objetivo es mantener el proyecto coherente a medida que crece:

- las máquinas deben implementarse con una estructura consistente
- el código sensible a rendimiento no debe degradarse durante refactors
- el código acelerado en Cython debe seguir siendo contrastable frente a referencias Python
- `save/load state` y debug deben seguir siendo capacidades de primer nivel

Estas reglas están pensadas para ser prácticas. Si un cambio entra en conflicto
con ellas, el cambio debe justificarse con claridad.

## 1. Responsabilidades del repositorio

### `machines/`

Los módulos de máquina son responsables del wiring:

- mapa de memoria
- mapa de puertos / conexión al bus
- slots de ROM o medios
- orquestación del stepping por frame
- serialización de estado
- exposición de dispositivos de debug

Los módulos de máquina no deben absorber lógica de chips reutilizables que
pertenezca a otra capa.

### `chipsets/`

`chipsets/` contiene bloques de hardware emulado reutilizables:

- chips de audio
- chips de vídeo
- chips de IO
- comportamiento de silicio reutilizable y sensible a temporización

Si un bloque es reutilizable entre varias máquinas y representa materialmente un
chip, pertenece aquí.

### `devices/`

`devices/` contiene helpers de memoria mapeada, medios y periféricos que no
encajan mejor como chip:

- helpers de cinta/disco/cartucho
- bloques de memoria mapeada
- periféricos o piezas auxiliares cercanas a la máquina

Ejemplos:

- `OpenBus`
- `ByteRAM`
- `NibbleRAM`

son `devices`, no internals de CPU ni hacks específicos de una sola máquina.

### `cpu/`

`cpu/` contiene núcleos de CPU y lógica genérica de bus/memoria adyacente al
procesador.

No debe acumular comportamiento específico de máquina salvo que ese
comportamiento forme realmente parte del core del procesador o de su contrato de
bus genérico.

### `tests/fallbacks/`

Las implementaciones de referencia en Python usadas como oráculos de corrección
o equivalencia pertenecen aquí.

Son activos de test, no fallbacks de producción.

## 2. Python primero, Cython después

El trabajo nuevo sobre una máquina o chip debe seguir este orden:

1. implementar primero el comportamiento en Python
2. añadir tests contra esa implementación Python
3. validar el comportamiento con software real cuando sea posible
4. sólo después mover caminos calientes a Cython
5. mantener la referencia Python en tests cuando sirva como oráculo de equivalencia

Esta regla existe para preservar depurabilidad y testabilidad.

## 3. Sin fallbacks de producción para chips cythonizados

Si un chip tiene una implementación de producción en Cython, producción debe
usar directamente esa implementación.

No deben mantenerse clases fallback Python en la ruta normal de imports de
producción para esos chips, salvo una razón operativa fuerte.

Las referencias Python de chips acelerados deben vivir en `tests/fallbacks/`.

Esto evita:

- divergencia silenciosa entre los caminos Python y Cython en producción
- imports accidentales de módulos obsoletos
- deriva arquitectónica donde las referencias de test se filtran al runtime

## 4. Reglas de rendimiento

El código sensible a rendimiento debe tratarse de forma distinta al código frío.

### Zonas seguras para refactor

Suelen ser zonas seguras para reorganizar sin riesgo de rendimiento:

- wiring de registry
- factories de máquinas
- resolución de ROMs/rutas
- validación de blobs de estado
- ensamblado de `debug_devices()`
- plumbing del CLI
- organización de tests
- documentación

### Hot paths

Estas zonas exigen más disciplina:

- stepping de CPU
- bucles `run_until()`
- stepping por frame
- renderizadores por scanline
- raster de sprites/tiles
- generación de muestras de audio
- lógica de mapper/bus por acceso

Los refactors que toquen hot paths no deben aceptarse a ciegas.

El proceso es:

1. medir la línea base de comportamiento o velocidad
2. hacer el cambio
3. volver a medir
4. rechazar el refactor si la regresión es relevante e injustificada

La limpieza estructural no es razón suficiente para ralentizar la emulación.

## 5. Estado y debug son de primer nivel

El soporte publicado de una máquina debe preservar:

- `read_state()`
- `write_state()`
- usabilidad de snapshots cuando aplique
- `debug_devices()`

El soporte de estado no es un detalle cosmético. Forma parte del contrato del
proyecto.

Si un chip o máquina nueva madura lo suficiente como para enviarse, debe
integrarse limpiamente con:

- guardado/restauración de estado en runtime
- inspección por debug
- escenarios de test deterministas cuando sea posible

## 6. Reglas de nombres

Usar nombres canónicos de hardware cuando sea práctico.

Ejemplos:

- usar nombres de chip como `TMS9918A`
- preferir nombres correctos de dominio como `Sega8VDP` frente a nombres
  heredados o engañosos ligados a una máquina concreta

Evitar nombres que oculten responsabilidades:

- no llamar `mappers` a bloques genéricos de memoria mapeada
- no mantener nombres de compatibilidad obsoletos como API pública salvo una
  necesidad real

Los aliases de compatibilidad pueden existir localmente, pero los nombres
canónicos deben dominar en código fuente, tests y exports.

## 7. Artefactos generados

Los artefactos generados no deben confundirse con código fuente.

El repositorio debe poder limpiarse rutinariamente de:

- `__pycache__/`
- `build/`
- `.pytest_cache/`
- `.tox/`
- `*.egg-info/`
- `*.pyc`
- `*.so`
- `*.c` generados por Cython
- salidas de cobertura

Usar:

```bash
tox -e clean
```

para eliminar artefactos generados del árbol del proyecto sin tocar `.git` ni
`.venv`.

Tras limpiar, reconstruir explícitamente:

```bash
.venv/bin/python setup.py build_ext --inplace
```

o:

```bash
.venv/bin/pip install ./
```

## 8. Disciplina de validación

Los tests son necesarios, pero no suficientes.

Cuando se cambie código de emulación, preferir una combinación de:

- tests unitarios
- tests de equivalencia frente a referencias Python
- tests de roundtrip de estado/debug
- smoke tests con software real: ROMs, discos, cintas o snapshots

Los huecos de cobertura no prueban automáticamente que un código esté muerto.
La cobertura debe leerse junto con:

- referencias/imports estáticos
- entry points reales de runtime
- reachability desde el machine registry
- caminos de ejecución con software real

## 9. Criterio de refactor

El refactor está incentivado cuando mejora:

- separación de responsabilidades
- nombres
- testabilidad
- depurabilidad
- consistencia entre máquinas

El refactor debe rechazarse cuando:

- mueve lógica caliente fuera de implementaciones eficientes sin justificación
- fusiona responsabilidades no relacionadas por comodidad
- introduce fallbacks de producción que diluyen la arquitectura
- debilita las garantías de estado/debug/tests

La preferencia por defecto es:

- helpers compartidos de camino frío: bien
- hacks específicos de máquina en capas genéricas: mal
- abstracciones genéricas: bien sólo si son genuinamente genéricas

No forzar abstracción pronto si la semántica sigue siendo específica de una
máquina.

## 10. Criterio de release

Antes de una release:

1. limpiar artefactos generados si hace falta
2. reconstruir desde cero
3. ejecutar los tests automáticos relevantes
4. hacer smoke tests con medios reales en las máquinas afectadas
5. actualizar changelog y TODO si el alcance cambió

Una release está lista cuando el camino enviado es coherente, está respaldado
por tests y no depende accidentalmente de artefactos obsoletos.
