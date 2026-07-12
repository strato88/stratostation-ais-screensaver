# AIS Radar Screensaver

Salvapantallas a pantalla completa estilo control de tráfico marítimo que muestra **tráfico real
de barcos** recibido a través del feed AIS gratuito de [aisstream.io](https://aisstream.io/) —
con barrido giratorio, estelas de posición, etiquetas sin solapes, y números que ruedan como una
caja registradora. **No hace falta receptor propio**: a diferencia de un montaje ADS-B típico, no
necesitas antena ni dongle SDR — solo una key gratuita.

![Salvapantallas radar AIS con tráfico marítimo real sobre Ibiza](docs/screenshot.png)

**Demo en vivo (tráfico real sobre Ibiza, ahora mismo):**
https://strato88.duckdns.org/ships/radar.html

[English version →](README.md)

## Qué necesitas

- Una key gratuita de [aisstream.io](https://aisstream.io/) (registro simple, sin pago, sin
  hardware).
- Python 3 + el paquete `websocket-client` (`pip install -r requirements.txt`) — a diferencia del
  [screensaver de radar ADS-B](https://github.com/strato88/stratostation-radar-screensaver) del
  mismo autor, este servidor **no** es solo librería estándar, porque necesita un cliente
  websocket.
- Un Mac o PC con Windows para el salvapantallas en sí.

## ⚠️ Una key, una conexión

**aisstream.io solo permite una conexión websocket activa por key.** Consigue tu propia key
gratuita — no reutilices la de otra persona, incluida la que alimenta la demo en vivo de arriba,
o las dos instancias competirán en silencio por la única conexión y una de ellas se irá
desconectando constantemente.

## Puesta en marcha

```bash
git clone https://github.com/strato88/stratostation-ais-screensaver.git
cd stratostation-ais-screensaver
pip install -r requirements.txt
```

1. **Configura el radar** — edita el bloque `CONFIG` al inicio del `<script>` de
   [radar.html](radar.html): latitud/longitud de tu estación, alcance visible, etiqueta de
   estación, idioma, velocidades de animación. Todo está comentado.

2. **Configura el servidor** — se pueden cambiar con variables de entorno:

   | Variable | Por defecto | Función |
   |---|---|---|
   | `AIS_PORT` | `8096` | puerto HTTP |
   | `AISSTREAM_KEY` | *(obligatoria)* | tu key gratuita de aisstream.io |
   | `AIS_LAT` | `38.8728` | latitud de la estación |
   | `AIS_LON` | `1.4015` | longitud de la estación |
   | `AIS_RANGE_NM` | `25` | radio de suscripción en millas náuticas — también define el bounding box de aisstream.io |
   | `AIS_PRUNE_S` | `2400` | olvidar un barco tras estos segundos sin mensajes |
   | `AIS_TRAIL_MAX` | `60` | puntos máximos de estela por barco |
   | `AIS_TRAIL_MIN_GAP_S` | `30` | segundos mínimos entre dos puntos de estela |
   | `AIS_DB_PATH` | *(sin definir)* | opcional — ruta a un fichero SQLite para persistir el estado de los barcos entre reinicios (ver abajo). Sin definir, funciona solo en memoria |
   | `AIS_SNAPSHOT_S` | `60` | cada cuánto se guarda el snapshot SQLite, si `AIS_DB_PATH` está definida |

3. **Arráncalo**:

   ```bash
   AISSTREAM_KEY=tu_key_aqui python3 server.py
   ```

   Abre `http://<host>:8096/radar.html` en un navegador para comprobar que funciona.
   Para dejarlo permanente, mira [examples/ais-radar.service](examples/ais-radar.service).

4. **(Opcional) publícalo** a través de tu proxy inverso / DNS dinámico si quieres que el
   salvapantallas funcione fuera de tu LAN. `/api/ships` solo reenvía datos de posición que los
   barcos ya emiten en abierto por VHF, pero revisa lo que expones como con cualquier servicio.

## Opcional: capa de costa

Coloca un fichero `coast.json` junto a `server.py` y el radar lo dibujará como costa — un array
JSON de polilíneas, cada una una lista de puntos `[lon, lat]`. El `coast.json` de la demo en vivo
(Ibiza y Formentera) se generó a partir de OpenStreetMap vía la API de Overpass, simplificado con
el algoritmo Douglas-Peucker. Es totalmente opcional — sin `coast.json`, el servidor simplemente
no publica esa ruta y el radar dibuja sin costa.

## Opcional: persistir el estado entre reinicios

Por defecto el servidor guarda el estado de los barcos solo en memoria — un reinicio empieza con
el mapa vacío, y puede tardar 10-15 minutos en repoblarse (la cadencia de AIS varía: Clase A
navegando cada 2-10 s, Clase B cada 30 s-3 min, datos estáticos como nombre/tipo solo cada ~6 min).

Define `AIS_DB_PATH` con una ruta de fichero (p. ej. `AIS_DB_PATH=ships.db`) para volcar el
estado completo de los barcos (incluidas las estelas) a SQLite cada `AIS_SNAPSHOT_S` segundos
(60 por defecto), y también al recibir una parada limpia (`SIGTERM`, p. ej. `systemctl stop`).
Al arrancar, el servidor restaura el último snapshot, descartando cualquier barco más viejo que
`AIS_PRUNE_S`. En el peor caso (caída brusca) la pérdida máxima es de un intervalo de snapshot.
Es opcional y está desactivado por defecto, así que un clon recién descargado se comporta igual
que antes.

## Instalar el salvapantallas

### macOS — instalación rápida (compilado, sin configuración)

Descarga **[AIS-Radar-Screensaver-macOS.zip](https://github.com/strato88/stratostation-ais-screensaver/releases/download/macos-v1.0/AIS-Radar-Screensaver-macOS.zip)**,
descomprime y haz doble clic en `AIS Radar.saver` — macOS ofrecerá instalarlo. Viene precargado
con el feed en vivo de Ibiza, y puedes apuntarlo a tu propio servidor desde **Opciones**. Al no
estar notarizado por Apple, si Gatekeeper lo bloquea ve a **Ajustes del Sistema → Privacidad y
Seguridad** y pulsa **Abrir de todos modos**.

### macOS — instalación manual (cargador genérico)

1. Descarga [WebViewScreenSaver](https://github.com/liquidx/webviewscreensaver/releases)
   (gratuito, código abierto) y haz doble clic en `WebViewScreenSaver.saver` para instalarlo.
   Si Gatekeeper protesta, autorízalo en **Ajustes del Sistema → Privacidad y Seguridad**.
2. **Ajustes del Sistema → Fondo de pantalla → Salvapantallas** → selecciona
   **WebViewScreenSaver** → **Opciones**:
   - Desmarca *Fetch URLs Remotely*.
   - En **Addresses**, borra la URL de ejemplo y añade la tuya:
     `http://<host>:8096/radar.html` (o tu URL pública HTTPS).
   - Pon en *Seconds* un valor grande (p. ej. `999999`) — la página ya refresca sola sus datos.
3. Varias pantallas: activa **"Mostrar en todas las pantallas"** junto a la vista previa.

### Windows

1. Instala [Lively Wallpaper](https://rocksdanister.github.io/lively/) (gratuito, código
   abierto) — usa la versión **installer**, no la de Microsoft Store, para que el salvapantallas
   funcione sin tener la app abierta.
2. En Lively: **+** → pestaña **Webpage/URL** → pega tu URL del radar.
3. Ajustes de Lively (engranaje) → pestaña **Screensaver** → activa usar el wallpaper actual
   como salvapantallas. Opcionalmente instala el `.scr` de Lively desde esa misma pestaña para
   elegirlo desde el diálogo nativo de salvapantallas de Windows.

## Cómo funciona

- `server.py` (~190 líneas) mantiene una única conexión websocket persistente a aisstream.io,
  acumula el estado de cada barco por MMSI (posición, velocidad, rumbo, nombre, tipo, destino),
  construye una estela de posición por barco, olvida los que dejan de emitir, y reenvía el estado
  actual como JSON en `/api/ships`.
- `radar.html` es una única página autocontenida: un `<canvas>` pinta anillos de distancia,
  barrido, estelas y blips a 60 fps, más una costa opcional; los datos se refrescan cada 5 s. Las
  etiquetas se colocan con un pequeño resolutor de colisiones que va probando posiciones en
  espiral hasta encontrar hueco. Los barcos navegando (velocidad ≥ 0,5 kt) se muestran como
  triángulos rotados con etiqueta de nombre/velocidad; los amarrados o fondeados se muestran como
  puntos simples sin etiqueta, para que los puertos con mucho tráfico sigan siendo legibles.
- Las fuentes ([Space Grotesk](https://github.com/floriankarsten/space-grotesk),
  [JetBrains Mono](https://github.com/JetBrains/JetBrainsMono)) van incluidas en `vendor/`
  bajo licencia SIL Open Font License, así la página funciona sin peticiones externas.

## Licencia

[MIT](LICENSE). Fuentes bajo [SIL OFL 1.1](vendor/FONT-LICENSES.md).
