Este documento define las reglas de ingeniería del proyecto y debe ser leído por los agentes que vayan a modificarlo.

## 1. Piensa antes de programar

**No des nada por hecho. No ocultes la confusión. Haz visibles las alternativas y sus implicaciones.**

Antes de implementar:

* Expón tus suposiciones explícitamente. Si tienes dudas, pregunta.
* Si existen varias interpretaciones posibles, preséntalas; no elijas una en silencio.
* Si existe un enfoque más simple, dilo. Cuestiona la idea cuando tenga sentido hacerlo.
* Si algo no está claro, detente. Explica qué resulta confuso. Pregunta.

## 2. La simplicidad primero

**El mínimo código necesario para resolver el problema. Nada especulativo.**

* No añadas funcionalidades más allá de lo solicitado.
* No crees abstracciones para código de un solo uso.
* No añadas "flexibilidad" ni "configurabilidad" que nadie pidió.
* No implementes manejo de errores para escenarios imposibles.
* Si escribes 200 líneas y podría resolverse con 50, reescríbelo.

Pregúntate: *"¿Diría un ingeniero sénior que esto es innecesariamente complicado?"* Si la respuesta es sí, simplifícalo.

## 3. Cambios quirúrgicos

**Toca solo lo imprescindible. Limpia únicamente el desorden que generes tú.**

Al modificar código existente:

* No "mejores" código, comentarios o formato cercanos que no están relacionados.
* No refactorices cosas que funcionan a menos que te lo pidan.
* Sigue el estilo existente, incluso si tú lo harías de otra manera.
* Si detectas código muerto no relacionado, menciónalo; no lo elimines.

Cuando tus cambios generen elementos huérfanos:

* Elimina importaciones, variables o funciones que TUS cambios hayan dejado sin uso.
* No elimines código muerto preexistente salvo que se solicite.

La prueba es simple: cada línea modificada debe poder relacionarse directamente con la petición del usuario.

## 4. Ejecución orientada a objetivos

**Define criterios de éxito. Itera hasta verificar el resultado.**

Transforma las tareas en objetivos verificables:

* "Añadir validación" → "Escribir pruebas para entradas inválidas y hacer que pasen"
* "Corregir el error" → "Escribir una prueba que lo reproduzca y hacer que pase"
* "Refactorizar X" → "Comprobar que las pruebas pasan antes y después"

Para tareas con varios pasos, define un plan breve:

```text
1. [Paso] → verificar: [comprobación]
2. [Paso] → verificar: [comprobación]
3. [Paso] → verificar: [comprobación]
```

Unos criterios de éxito sólidos permiten trabajar de forma autónoma. Los criterios débiles ("haz que funcione") obligan a pedir aclaraciones constantemente.

## 5. El proyecto

El proyecto debe mantenerse coherente a medida que crece:

- las máquinas deben implementarse con una estructura consistente
- el código sensible a rendimiento no debe degradarse durante refactors
- el código acelerado en Cython debe seguir siendo contrastable frente a referencias Python
- `save/load state` y debug deben seguir siendo capacidades de primer nivel

Estas reglas están pensadas para ser prácticas. Si un cambio entra en conflicto
con ellas, el cambio debe justificarse con claridad.

### 5.1. Responsabilidades del repositorio

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

### 5.2. Python primero, Cython después

El trabajo nuevo sobre una máquina o chip debe seguir este orden:

1. implementar primero el comportamiento en Python
2. añadir tests contra esa implementación Python
3. validar el comportamiento con software real cuando sea posible
4. sólo después mover caminos calientes a Cython
5. mantener la referencia Python en tests cuando sirva como oráculo de equivalencia

Esta regla existe para preservar depurabilidad y testabilidad.

### 5.3. Sin fallbacks de producción para chips cythonizados

Si un chip tiene una implementación de producción en Cython, producción debe
usar directamente esa implementación.

No deben mantenerse clases fallback Python en la ruta normal de imports de
producción para esos chips, salvo una razón operativa fuerte.

Las referencias Python de chips acelerados deben vivir en `tests/fallbacks/`.

Esto evita:

- divergencia silenciosa entre los caminos Python y Cython en producción
- imports accidentales de módulos obsoletos
- deriva arquitectónica donde las referencias de test se filtran al runtime

### 5.4. Estado y debug son de primer nivel

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

### 5.5. Reglas de nombres

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

### 5.6. Artefactos generados

Los artefactos generados no deben confundirse con código fuente.

El repositorio debe poder limpiarse bajo demanda o antes de una release de:

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

### 5.7. Disciplina de validación

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

### 5.8. Criterio de release

Antes de una release:

1. limpiar artefactos generados si hace falta
2. reconstruir desde cero
3. ejecutar los tests automáticos
4. hacer smoke tests con medios reales en las máquinas afectadas
5. actualizar changelog, readme y TODO si el alcance cambió

Una release está lista cuando el camino enviado es coherente, está respaldado
por tests y no depende accidentalmente de artefactos obsoletos.
