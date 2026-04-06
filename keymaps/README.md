# Keymaps

Los keymaps de `MultiEmu` se definen en JSON y sirven para describir:

- teclas simples del host
- combinaciones con modificadores
- combinaciones resueltas por `unicode`
- mappings de gamepad/joystick

Los ficheros por defecto viven en esta carpeta y pueden reutilizarse como base
para layouts específicos por máquina, idioma o teclado físico.

## Búsqueda

Cuando un frontend necesita un keymap por id, lo busca en este orden:

1. `$CWD/keymaps/`
2. `/usr/local/share/multiemu/keymaps`
3. `/usr/share/multiemu/keymaps`
4. `/etc/multiemu/keymaps`
5. `$HOME/.local/share/multiemu/keymaps`

También se puede pasar un fichero explícito con `--keymap`.

## Estructura

Ejemplo mínimo:

```json
{
  "id": "spectrum128k_es",
  "base": "spectrum128k",
  "keys": {
    "K_a": [1, 0]
  },
  "combos": [
    {
      "key": "K_LEFT",
      "mod": "KMOD_NONE",
      "controls": [[0, 0], [3, 4]]
    }
  ],
  "unicode_combos": {
    "+": [[7, 1], [6, 2]]
  },
  "gamepad": {
    "dpad_left": "JOYSTICK_LEFT",
    "button_south": "JOYSTICK_FIRE"
  }
}
```

Campos:

- `id`: identificador del keymap.
- `base`: keymap base del que heredar.
- `keys`: mapeo directo `tecla pygame -> control emulado`.
- `combos`: combinación de `key + mod` del host que activa varios controles.
- `unicode_combos`: símbolo Unicode ya resuelto por el layout del host.
- `gamepad`: mapeo de botones/ejes lógicos del mando.

## Keys

`keys` usa constantes de `pygame`, por ejemplo:

- `K_a`
- `K_RETURN`
- `K_BACKSPACE`
- `K_LEFT`

Cada valor es:

```json
[control_a, control_b]
```

En máquinas de teclado matricial suele ser:

- `control_a = fila`
- `control_b = bit/columna`

## Combos

`combos` sirve para teclas del host que en la máquina emulada equivalen a más
de una tecla pulsada.

Ejemplo:

```json
{
  "key": "K_BACKSPACE",
  "mod": "KMOD_NONE",
  "controls": [[0, 0], [4, 0]]
}
```

`mod` también usa constantes de `pygame`, por ejemplo:

- `KMOD_NONE`
- `KMOD_SHIFT`
- `KMOD_MODE`

## Unicode Combos

`unicode_combos` es útil cuando el layout del host no coincide con el de la
máquina emulada. En vez de depender de la tecla física, se usa el carácter que
`pygame` ya ha resuelto.

Ejemplo:

```json
{
  "+": [[7, 1], [6, 2]],
  "/": [[7, 1], [0, 4]]
}
```

Esto suele ser la vía correcta para símbolos en layouts nacionales.

## Gamepad y joystick

`gamepad` usa nombres lógicos estables:

- `dpad_up`
- `dpad_right`
- `dpad_down`
- `dpad_left`
- `button_south`
- `button_east`
- `button_start`
- `button_select`

El valor puede ser:

- una señal de joystick clásica:
  - `JOYSTICK_UP`
  - `JOYSTICK_RIGHT`
  - `JOYSTICK_DOWN`
  - `JOYSTICK_LEFT`
  - `JOYSTICK_FIRE`
  - `JOYSTICK_FIRE_2`
- o un control matricial `[control_a, control_b]`, como en consolas con pad
  propio.

Ejemplos:

```json
{
  "dpad_left": "JOYSTICK_LEFT",
  "button_south": "JOYSTICK_FIRE"
}
```

```json
{
  "button_south": [1, 0],
  "button_east": [1, 1]
}
```

## Herencia

La forma recomendada de crear un keymap nuevo es partir de uno existente con
`base` y sobrescribir solo las diferencias.

Ejemplo:

```json
{
  "id": "spectrum128k_custom",
  "base": "spectrum128k",
  "unicode_combos": {
    "-": [[7, 1], [6, 3]]
  }
}
```

## Recomendaciones

- Deja en `keys` solo la matriz base de la máquina.
- Usa `combos` para atajos tipo cursores o teclas compuestas.
- Usa `unicode_combos` para símbolos dependientes del layout del host.
- Si una máquina tiene variantes con teclado distinto, crea un fichero por
  máquina, no un único keymap genérico.
