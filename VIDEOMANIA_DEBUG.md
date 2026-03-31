# VIDEOMANIA Debug

Estado de la investigación sobre `roms/Videomania.prg` en `vic20ntsc`.

## Comando de referencia

```bash
multiemu run vic20ntsc --frontend pygame \
  --rom basic=roms/basic.901486-01.bin \
  --rom kernal=roms/kernal.901486-07.bin \
  --rom char=roms/characters.901460-03.bin \
  --rom cart=roms/Videomania.prg
```

## Síntoma observado

- El cartucho arranca.
- Hace un self-test visible durante varios segundos.
- La música sigue sonando continuamente.
- La imagen parece quedar congelada hacia los `19-20` segundos.

Conclusión inmediata:

- No parece un cuelgue global de CPU.
- No parece un fallo de carga de cartucho.
- El problema es visual o de lógica de juego, no de que la máquina entera deje de ejecutar.

## Estado del hardware durante el caso

Tras la fase de self-test, los registros del `VIC-I` quedan típicamente así:

- `9005 = 0x8C`
- `900E = 0x7F`
- `900F = 0x08`

Interpretación:

- `screen base = 0x1200`
- `char base = 0x1000`

Es decir:

- la pantalla visible depende de `screen RAM` en `0x1200`
- y de caracteres redefinidos en RAM en `0x1000`

## Comprobaciones relevantes

### 1. La CPU sigue viva

Tras `200` frames:

- `PC = 0xA759`
- en los últimos `80` frames hubo `29` PCs distintos

Ejemplo de distribución en ventanas de `60` frames:

- `0-59`: `29` PCs únicos
- `60-119`: `24`
- `120-179`: `27`
- `180-239`: `22`
- `240-299`: `21`

PCs más frecuentes en fase estable:

- `0xA750`
- `0xA752`
- `0xA754`
- `0xA755`
- `0xA768`
- `0xA759`

Conclusión:

- No está clavado en una sola instrucción.
- Sigue ejecutando una rutina estable de trabajo.

### 2. El framebuffer sí deja de cambiar

Muestreo cada `30` frames:

- `frame 0`: `fb = fa91da25566a`
- `frame 60`: `fb = e9d1ffd3cac0`
- `frame 90`: `fb = c4160d4b2150`
- `frame 120`: mismo hash que `frame 90`
- `frame 150`: mismo hash
- `frame 180`: mismo hash
- `frame 210`: mismo hash
- `frame 240`: mismo hash
- `frame 270`: mismo hash
- `frame 300`: mismo hash

Cambios observados:

- `frame 60 -> 90`: `fb_diff = 21834`
- `frame 90 -> 120`: `fb_diff = 0`
- desde ahí: `fb_diff = 0`

Conclusión:

- La imagen sí entra en un estado estable real.

### 3. El charset en RAM también deja de cambiar

Muestreo del bloque `0x1000-0x10FF`:

- `frame 0`: hash `b376885ac845`
- `frame 60`: mismo hash
- `frame 90`: hash `af507e2ee3be`
- `frame 120`: mismo hash que `frame 90`
- desde ahí: estable

Cambios observados:

- `frame 60 -> 90`: `chr_diff = 33`
- `frame 90 -> 120`: `chr_diff = 0`
- desde ahí: `chr_diff = 0`

Cabecera típica en `0x1000` desde la fase estable:

```text
3C 42 46 5A 62 46 30 0B 01 01 06 03 00 00 00 00
```

Conclusión:

- No es un bug de “el VIC no refresca chars que siguen cambiando”.
- El propio charset deja de mutar.

### 4. La screen RAM se queda plana

Cabecera típica de `0x1200`:

```text
00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
```

Conclusión:

- La imagen visible depende de repetir el carácter `0` usando un glyph redefinido en RAM.
- No hay screen codes variados que permitan inferir estados más altos de juego desde pantalla RAM.

## Rutinas desensambladas relevantes

### A721 / A740-A76A

Bloque observado:

```text
A720: 60 8A 48 A5 04 4A 4A 4A AA BD 70 A7 85 01 BD 86
A730: A7 18 65 05 85 00 A5 01 69 00 85 01 A5 04 29 07
A740: 85 0B A0 07 B1 09 85 13 A9 00 85 14 A6 0B F0 07
A750: 46 13 66 14 CA D0 F9 B1 00 45 13 91 00 98 AA 09
A760: B0 A8 B1 00 45 14 91 00 8A A8 88 10 D7 68 AA 60
```

Interpretación funcional:

- usa `($09),Y` como fuente
- construye una máscara en `$13/$14`
- hace `EOR` sobre `($00),Y`
- recorre `8` filas por carácter

Conclusión:

- Es una rutina activa de transformación/dibujo, no un simple wait loop.

### A023

Zona:

```text
A023: 85 09 A9 00 85 0A 06 09 26 0A 06 09 26 0A 06 09 26
A033: 0A A5 0A 09 88 85 0A 4C 21 A7
```

Interpretación:

- prepara un puntero en `$09/$0A`
- luego salta a `A721`

Conclusión:

- `A023` es un helper/prefacio para `A721`
- no parece el punto del bloqueo

### A0F1

Zona:

```text
A0F1: CC 85 05 BD 3E A0 20 23 A0 20 3B A4 CA 10 BE 20
A101: 84 A8 29 20 F0 07 C6 0C D0 B1 4C 62 A1 60
```

Interpretación:

- carga `$04/$05`
- llama a `A023`
- llama a `A43B`
- sigue lógica de control en `A4xx/A8xx/A1xx`

Conclusión:

- Es un bloque de alto nivel más interesante que el propio worker gráfico

### A43A / A43B

Zona:

```text
A43A: 60
A43B: E6 0F
A43D: A5 0F
A43F: 29 3F
A441: D0 F7
A443: 8A 48 A9 A4 85 01 A9 7D 85 00 20 7D A0
A44D: 20 7D A0 20 7D A0 ...
```

Interpretación:

- incrementa `$0F`
- espera hasta que `($0F & 0x3F) == 0`
- luego llama repetidamente a `A07D`
- después escribe en registros de sonido `900A/900B/900C`

Conclusión:

- Esto encaja muy bien con temporización/driver de música
- explica por qué el audio sigue vivo aunque la imagen no avance

## Trazas de ejecución en fase estable

### PCs frecuentes en cola

Ejemplo de cola `frames 90-129`:

```text
0xA768, 0xA750, 0xA744, 0xA744, 0xA750, 0xA74E, 0xA752, ...
```

Más frecuentes:

- `0xA750`
- `0xA768`
- `0xA754`
- `0xA744`
- `0xA752`

### Trace a nivel de instrucción alrededor de A023/A0F1/A43A

Partiendo de `frame 90`, en `5000` steps:

- `A0F1 -> A023 -> A43B/A43A -> A023 -> ...`
- `X` va bajando `0x0A -> 0x09 -> 0x08 -> ...`
- `$0F` va subiendo `0x33 -> 0x34 -> 0x35 -> ...`

Ejemplo real:

```text
292  0xA0F1  X=0x0A  0F=0x33
295  0xA023  X=0x0A  0F=0x33
492  0xA43B  X=0x0A  0F=0x33
496  0xA43A  X=0x0A  0F=0x34
505  0xA023  X=0x09  0F=0x34
...
4445 0xA43A  X=0x03  0F=0x3B
4454 0xA023  X=0x02  0F=0x3B
```

Conclusión:

- La secuencia sigue viva y temporizada
- no es una CPU muerta
- pero ya no produce cambios visuales a partir de cierto punto

## Qué NO parece ser

- No parece un fallo de carga del cartucho
- No parece un cuelgue general del `m6502`
- No parece un fallo de refresco del `VIC-I` sobre un charset que siga cambiando
- No parece que `A721` esté escribiendo datos visuales que luego no se vean

## Qué SÍ parece ahora

La hipótesis más fuerte es:

- la lógica de alto nivel del cartucho entra en una fase estable
- la música sigue porque `A43B/A07D` siguen funcionando
- pero la transición al siguiente estado visual no ocurre porque una condición previa de control no se satisface

Los candidatos más claros ya no están en el renderer del `VIC-I`, sino en la lógica del cartucho alrededor de:

- `A0F1`
- `A101`
- `A4xx`
- `A8xx`
- `AA46`

## Siguiente paso recomendado

Seguir por la lógica de control, no por vídeo:

1. desmontar la ruta de alto nivel que alimenta `A0F1`
2. localizar la condición que debería sacar al programa de la fase de self-test
3. revisar especialmente:
   - `A101`
   - `A84x`
   - `AA46`
   - llamadas a `ADxx/AFxx`
4. contrastar si depende de:
   - teclado
   - `VIA`
   - temporización
   - flags/contadores en RAM

Si se retoma esta investigación en otra sesión, no volver a empezar por el `VIC-I`: el cuello de botella actual de `Videomania` ya no parece estar ahí.
