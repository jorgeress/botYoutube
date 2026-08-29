# Decisiones de diseño

Notas de por qué cada cosa está como está. Casi todas salieron de algo que
falló primero.

## El prompt negativo es inerte

Flux Schnell va fijo a `cfg=1.0`, y a `cfg=1.0` el prompt negativo no hace
absolutamente nada. Todo el control de calidad tiene que salir de cómo está
escrito el prompt positivo. Las listas de cosas prohibidas no solo no servían:
se comían parte del presupuesto de atención, que son tres o cuatro elementos por
imagen. Solo merece la pena meter los tres o cuatro elementos correctos.

## Campos cerrados en vez de prosa libre

Antes cada beat llevaba un `(visual ...)` en texto libre y una función
`enrich_visual()` que lo intentaba arreglar a base de expresiones regulares. Eso
se convirtió en una espiral de mantenimiento: cada guion nuevo rompía una regex
y arreglarla rompía otra cosa.

La raíz del problema es que Flux Schnell a 4 pasos y `cfg=1.0` atiende a unos
tres o cuatro elementos, y con el negativo muerto no hay forma de corregir lo
que elija. Con campos de vocabulario cerrado, montar el prompt es buscar en un
diccionario: sale igual dos veces seguidas y se puede validar antes de generar.

`prompts/beat_format.md` es la especificación y `scripts/_catalog.py` la fuente
de verdad en código.

## La descripción del personaje se inyecta sola

`CHARACTER_ANCHOR` nunca se escribe en el guion. El pipeline lo mete en todos
los beats con `char >= 1`. Es lo que más mejoró la consistencia del personaje
entre cuadros, porque quita de en medio la posibilidad de describirlo distinto
cada vez.

## Semilla por segmento, no por índice global

`base = sha256(out_dir:segment_id)` y luego `seed = base + índice del beat
dentro del segmento`. Así los beats del mismo segmento comparten una base de
estilo. Antes la semilla salía del índice global y el estilo pegaba saltos
arbitrarios entre dos beats consecutivos.

## El ancla de estilo, por debajo de 20 palabras

`IMAGE_STYLE_A` está en 15 palabras. Las descripciones de estilo largas quemaban
atención a `cfg=1.0` y no aportaban nada medible.

## Fuera los overlays de PIL

`_overlay.py` y el tipo de beat `data_frame` se eliminaron. Añadían complejidad,
daban resultados inconsistentes y generaban ruido de doble dibujado, porque PIL
y Flux acababan pintando el mismo elemento. La calidad se controla desde el
prompt.

Los beats `text-frame` sí siguen con PIL, porque para texto grande y limpio no
hay color: un modelo de difusión escribe mal.

## Ritmo de voz natural

`TTS_SPEED = 1.0`, `EXAGGERATION = 0.3`, `CFG = 2.0`. Estirar el tiempo con
`atempo` por debajo de 0,9x suena a robot, así que el ritmo hay que conseguirlo
escribiendo el guion con comas donde tocan, no en post.

Huecos entre beats: 250 ms dentro del mismo segmento y 500 ms al cambiar de
segmento.

## Fundido a negro en vez de Ken Burns

El zoom lento de Ken Burns producía un temblor visible. Lo sustituí por 0,05
segundos de entrada y salida en fundido (`_FADE_DUR` en `_comfyui.py`).

## Solo `h264_nvenc`

El FFmpeg instalado (versión n7.1) está compilado con `--disable-libx264`. Todo
el encoding va por el encoder de la GPU. Ya está puesto en `_comfyui.py` y en
`assemble_video.py`.

## Iconos en los rótulos

`build_sprites()`, en `generate_image_prompts.py`, elige un icono temático para
cada beat de tipo `text-frame` a partir de la palabra clave del campo `text:`.
El icono se compone encima del texto en `_apply_post_effects()`, y
`_text_frame.render_text_frame(icon_top=True)` baja el texto al 62% inferior del
cuadro para dejarle sitio.

## Los subtítulos se cortan en los límites de beat

`generate_subtitles.py` mete un centinela `_force_break` después de las palabras
de cada beat, para que ningún bloque de subtítulo se quede a caballo entre dos
beats. Así el texto en pantalla siempre corresponde a la imagen que se está
viendo.
