# Changelog

Este fichero resume hitos visibles del proyecto por versión publicada.

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
