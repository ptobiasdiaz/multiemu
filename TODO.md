# TO-DO

## Prioridad actual

1. Validar más ROMs reales de `msx`, `colecovision`, `gamegear` y `mastersystem2`.
2. Medir rendimiento real de MSX tras `MSXMemoryMap` Cython y AY sobremuestreado x2.
3. Decidir el siguiente cuello del CPC antes de mover más código a Cython.
4. Seguir afinando `AY38912` como chip común, no como forks por máquina.
5. Ampliar compatibilidad de MSX con más mappers, más cintas `.cas` y futura línea MSX2 separada.

## Componentes compartidos

### AY38912

Estado actual:

- Se usa en CPC, Spectrum 128K/+2 y MSX.
- La ruta MSX renderiza audio progresivo con flush antes de escrituras y sobremuestreo interno moderado.
- Debe mantenerse como dispositivo común reutilizable entre arquitecturas.

Pendiente:

- [ ] Medir mejor el estado real de `AY38912` en las máquinas que ya lo usan.
- [ ] Revisar si el siguiente cuello del `AY38912` es rendimiento o fidelidad.
- [ ] Afinar mezcla, envolventes, temporización y diferencias audibles frente a hardware real.
- [ ] Evitar forks por máquina salvo que haya una diferencia real de cableado o reloj.

### TMS9918A

Estado actual:

- Se usa en MSX y ColecoVision.
- Cubre mejor sprites, Graphics II y vblank/status/IRQ.
- Tiene implementación Cython y referencia Python en tests.

Pendiente:

- [ ] Afinar prioridades raras, flags límite y timings menos comunes.
- [ ] Validar más software real de MSX y ColecoVision.
- [ ] Revisar desplazamientos de pantalla/carga observables en casos MSX reales.
- [ ] Medir rendimiento real tras la cythonización.

### OSD de medios

Estado actual:

- Hay OSD breve de actividad de cinta, incluyendo `CAS xx%`.
- La señal de actividad se expone también para el cliente TCP.

Pendiente:

- [ ] Revisar si conviene evolucionarlo a una API común para todos los medios y máquinas.
- [ ] Mantener la integración fuera del hot path de emulación.

### Frontend / teclado

Estado actual:

- CPC y Spectrum pueden perder alguna pulsación muy rápida en escenarios de repetición.
- La causa probable está más cerca del frontend/cadencia de escaneo que del mapa de teclado de cada máquina.

Pendiente:

- [ ] Revisar si `TAP_HOLD_FRAMES` y `QUICK_TAP_MAX_FRAMES` deben ajustarse por máquina.
- [ ] Comprobar si Spectrum necesita un perfil distinto del CPC para teclas repetidas.
- [ ] Si sigue fallando, instrumentar secuencias `KEYDOWN/KEYUP` repetidas en el frontend antes de tocar las máquinas.
- [ ] Revisar si `Enter` en CPC conserva alguna pérdida ocasional.

## Máquinas existentes

### MSX

Estado actual:

- `msx` arranca BIOS+BASIC y cartuchos MSX1 simples.
- Tiene soporte inicial de mappers MegaROM comunes.
- Tiene ROM DB local `romdb/msx_mappers.json` indexada por claves `sha1:<hash>`.
- Admite override de mapper con `--emu-ops cart1_mapper=...` y `cart2_mapper=...`.
- Tiene entrada por teclado y joystick emulado.
- Tiene soporte inicial de cassette `.cas` por hooks BIOS `TAPION/TAPIN/TAPIOF`.
- Usa `TMS9918A`, `AY38912` y `MSXMemoryMap` Cython.

Pendiente:

- [ ] Validar más cartuchos reales y ampliar `romdb/msx_mappers.json` con hashes SHA1 confirmados.
- [ ] Validar más cintas `.cas` reales y ajustar semántica de bloques `TAPION/TAPIN`.
- [ ] Medir rendimiento real con ROMs representativas tras `MSXMemoryMap` Cython y AY x2.
- [ ] Afinar fidelidad de vídeo TMS9918A en casos MSX reales.
- [ ] Mantener MSX2 como máquina separada.

### ColecoVision

Estado actual:

- `colecovision` existe como máquina visible.
- BIOS + cartucho funcionales con juegos reales ya jugables.
- `TMS9918A` y `SN76489` funcionan con save/load state y debug.
- El keypad y los dos botones del mando tienen keymap usable en teclado host.
- La música y timing básico de juegos reales ya están razonablemente afinados.

Pendiente:

- [ ] Seguir probando compatibilidad con más cartuchos reales.
- [ ] Afinar fidelidad fina del `TMS9918A` en casos límite.
- [ ] Afinar fidelidad fina del `SN76489` frente a hardware real.
- [ ] Revisar si conviene modelar los mandos Coleco como dispositivo separado.
- [ ] Medir rendimiento real tras la cythonización del `TMS9918A`.

### Master System II

Estado actual:

- `mastersystem2` arranca cartuchos `.sms`.
- La BIOS europea con juego built-in arranca sin cartucho.
- BIOS + cartucho reproduce el flujo esperado: logo BIOS y salto al cartucho.
- VDP y `SN76489` viven como chips Cython con referencia Python en tests.
- `F12`/`--state` y debug devices cumplen el contrato de hardware trazable.

Pendiente:

- [ ] Seguir afinando compatibilidad con más juegos reales.
- [ ] Mejorar fidelidad fina de VDP: timing por scanline/dot, flags raros y modos no usados por los tests actuales.
- [ ] Mejorar fidelidad fina de `SN76489`: volumen, ruido, mezcla y diferencias audibles frente a hardware real.
- [ ] Revisar si conviene separar cartucho/BIOS/mapper como clases de dispositivo reales.
- [ ] Medir rendimiento tras la cythonización antes de tocar más código caliente.

### Game Gear

Estado actual:

- `gamegear` existe como máquina visible basada en la línea SMS2.
- Reutiliza Z80, mapper base, VDP y `SN76489`.
- Expone resolución visible `160x144` mediante recorte del framebuffer SMS2.
- Usa CRAM/paleta Game Gear de 12 bits.
- Tiene keymap propio, botones `1`/`2` y botón `START`.
- Implementa puertos básicos `0x00-0x06`, incluyendo registro estéreo PSG.
- Emite audio estéreo real a través del contrato `audio_channels`.
- Participa en `F12`/`--state` y tests de roundtrip.
- Se ha probado con una batería inicial de ROMs reales `.gg`.

Pendiente:

- [ ] Seguir probando compatibilidad con más ROMs reales `.gg`.
- [ ] Añadir BIOS Game Gear si aparece software que la necesite.
- [ ] Implementar link/serial port real si se quiere soportar cable link.
- [ ] Decidir si el VDP debe parametrizar explícitamente modo SMS/GG en vez de usar recorte desde el framebuffer base.
- [ ] Afinar diferencias finas de timing VDP/PSG frente a hardware real.

### CPC

Estado actual:

- `cpc464`, `cpc664` y `cpc6128` existen como máquinas visibles.
- El vídeo depende del conjunto `Gate Array + CRTC`.
- El teclado funciona bastante bien y el autorepeat parece razonable.
- Puede haber pérdidas ocasionales en pulsaciones muy rápidas.

Pendiente:

- [ ] Medir el impacto real del camino `rgb24` del CPC.
- [ ] Decidir el siguiente cuello de botella del CPC antes de mover más código a Cython.
- [ ] Decidir si el siguiente paso prioritario es fidelidad de vídeo, audio o periféricos pendientes.
- [ ] Documentar con claridad que el vídeo CPC depende de `Gate Array + CRTC`, no de un único chip tipo ULA.
- [ ] Si reaparecen pérdidas de teclado, revisar primero el frontend de eventos antes que la máquina CPC.

### Spectrum

Estado actual:

- Spectrum sigue siendo referencia de arquitectura: máquina en Python, dispositivos encapsulados y aceleración sólo dentro del dispositivo caliente.
- `spectrum128k` y `spectrumplus2` usan AY básico.
- Algunas pulsaciones repetidas rápidas pueden perderse, por ejemplo `"iii"` acaba como `"ii"`.

Pendiente:

- [ ] Mantener Spectrum como referencia de arquitectura del proyecto.
- [ ] Revisar perfil de taps cortos si reaparecen pérdidas de teclado.
- [ ] Seguir afinando AY en paralelo con el chip común.

### Game Boy

Estado actual:

- `gameboy` y `gameboycolor` existen como máquinas visibles experimentales.
- Hay rutas Cython importantes para CPU/dispositivos.

Pendiente:

- [ ] Cerrar la brecha entre `cpu/lr35902/core.py` y `core.pyx`.
- [ ] No añadir opcodes o semántica nueva sólo en Cython; la referencia Python debe ir primero o en paralelo.
- [ ] Añadir test de equivalencia cuando se cierre esa brecha.
- [ ] Seguir afinando MMIO, timing fino por dot/cycle y cobertura con ROMs reales.

## Documentación

Pendiente:

- [ ] Mantener README y CHANGELOG alineados con máquinas visibles y slots reales.
- [ ] Documentar comandos representativos por máquina cuando se estabilicen nuevas rutas.
- [ ] Documentar el estado experimental de MSX1 y la separación prevista de MSX2.

## Backlog de máquinas nuevas

### 8 bits

- [ ] `MSX-2`
- [ ] `Vectrex`
- [ ] `Videopac G4000`
- [ ] `Atari 2600`
- [ ] `Atari Lynx`
- [ ] `NES`
- [ ] `Commodore 64`
- [ ] `Commodore 128`

### 16 bits

- [ ] `Amiga 500`
- [ ] `Atari ST`
- [ ] `Snes`
- [ ] `Megadrive`
- [ ] `PC AT`
