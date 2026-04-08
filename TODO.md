# TO-DO

## CPC464

### Video

- [ ] Medir el impacto real del camino `rgb24` del CPC.
  Comparar FPS/carga con el camino anterior para saber cuanto queda todavia en frontend frente a dispositivo.
- [ ] Decidir el siguiente cuello de botella del CPC antes de mover mas codigo a Cython.
  La regla debe seguir siendo: dispositivo caliente en Cython, maquina en Python.
- [ ] Decidir si el siguiente paso prioritario es mas fidelidad de video o perifericos pendientes.

### AY / Audio

- [ ] Medir mejor el estado real de `AY38912` en las maquinas que ya lo usan
  (`CPC`, `Spectrum 128K` y futuras maquinas con AY) antes de tocar mas codigo.
- [ ] Seguir afinando fidelidad de `AY38912`:
  mezcla, envolventes, temporizacion y diferencias observables frente a
  hardware/software real.
- [ ] Mantener `AY38912` como dispositivo comun reutilizable entre
  arquitecturas, evitando forks por maquina salvo que haya una diferencia real
  de cableado o reloj.
- [ ] Revisar si el siguiente cuello del `AY38912` es realmente de rendimiento
  o ya es principalmente de fidelidad.

### Teclado

Estado actual:

- el teclado CPC funciona bastante bien
- el autorepeat parece razonable
- aun pueden perderse algunas pulsaciones muy rapidas, pero mucho menos que antes

Pendiente:

- [ ] Revisar si `Enter` sigue teniendo alguna perdida ocasional
- [ ] Si reaparece el problema, revisar primero el frontend de eventos antes que la maquina CPC

## Spectrum

### Arquitectura

- [ ] Mantener Spectrum como referencia de arquitectura:
  maquina en Python, dispositivos encapsulados, aceleracion solo dentro del dispositivo caliente.

### Teclado

Problema observado:

- algunas pulsaciones repetidas rapidas tambien pueden perderse en Spectrum
- ejemplo observado: `"iii"` acaba como `"ii"`

Interpretacion actual:

- no parece un problema especifico del mapa de teclado Spectrum
- apunta mas bien a frontend/cadencia de escaneo y a como se estiran taps cortos

Siguiente paso:

- [ ] Revisar si `TAP_HOLD_FRAMES` y `QUICK_TAP_MAX_FRAMES` deben ajustarse por maquina
- [ ] Comprobar si Spectrum necesita un perfil distinto del CPC para teclas repetidas
- [ ] Si sigue fallando, instrumentar secuencias `KEYDOWN/KEYUP` repetidas en el frontend antes de tocar la maquina Spectrum

## Documentacion

- [ ] Dejar documentado con claridad que, en CPC, el video depende del conjunto `Gate Array + CRTC`, no de un unico chip tipo ULA.

## Game Boy

- [ ] Cerrar la brecha actual entre `cpu/lr35902/core.py` y `core.pyx`.
  Regla: no seguir metiendo opcodes o semantica nueva solo en Cython; la
  referencia Python debe ir primero o en paralelo y debe quedar test de
  equivalencia.
- [ ] Seguir afinando fidelidad y rendimiento cuando se retome esta linea.
  Prioridades razonables:
  MMIO, timing fino por dot/cycle y cobertura adicional con ROMs reales.

## Nuevas maquinas de 8 bits

- [ ] `Game Gear`
- [ ] `Master System II`
- [ ] `MSX`
- [ ] `MSX-2`
- [ ] `ColecoVision`
- [ ] `Vectrex`
- [ ] `Videopac G4000`
- [ ] `Atari 2600`

## Orden recomendado

1. Medir rendimiento real del CPC tras la nueva arquitectura de video.
2. Decidir si el siguiente paso prioritario es mas fidelidad de video o perifericos pendientes.
3. Seguir afinando `AY38912`.
4. Revisar si el siguiente frente en CPC debe ser audio/fidelidad o teclado/eventos.
