# Changelog

Este fichero resume hitos visibles del proyecto por versión publicada.

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
