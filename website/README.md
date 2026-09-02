# Olin — sitio público

Sitio institucional y demo explicativa de Olin. Está construido como sitio estático con Astro y usa React + Motion solo en las tres experiencias interactivas. No modifica ni ejecuta el motor de crédito.

## Ejecutar localmente

Requiere Node.js 22+ y pnpm.

```sh
pnpm install
cp public/config.example.js public/config.js
pnpm dev
```

Abrir `http://127.0.0.1:8001/`.

## Verificación

```sh
pnpm test
```

Esto comprueba tipos, genera las rutas estáticas y valida enlaces, recursos, estructura de títulos, la lista de espera y archivos de video.

## Configuración del demo

`public/config.js` no se versiona. Debe existir en cada entorno:

```js
const OLIN_DEMO_URL = "https://demo.ejemplo.mx";
const OLIN_WAITLIST_API_URL = "https://api.ejemplo.mx/api/v1/waitlist";
```

Para la implementación Fly.io de este proyecto, puede copiar
`public/config.production.example.js` a `public/config.js`. El formulario de
`/lista-espera/` quedará conectado a `https://olin-scoring-mvp.fly.dev/api/v1/waitlist`.
Si usa un dominio de API distinto, actualice también `OLIN_WAITLIST_ALLOWED_ORIGINS`
en el servicio Python y `connect-src` en `public/_headers`.

En una página pública HTTPS, Olin rechaza como destino una URL local o sin HTTPS. Si no hay URL válida, los botones llevan al caso ilustrativo dentro del sitio.

## Lista de espera

La ruta `/lista-espera/` contiene una solicitud B2B de dos pasos. El API público
`GET/POST /api/v1/waitlist` vive en el servicio Python. El contador muestra
solicitudes activas reales; no usa un número inicial ficticio. Los correos se
cifran y una huella HMAC evita que un envío duplicado aumente el contador.

Antes de habilitar el formulario en producción:

1. Generar y guardar `OLIN_WAITLIST_ENCRYPTION_KEY` como secreto de la plataforma.
2. Definir `OLIN_WAITLIST_ALLOWED_ORIGINS` con el dominio público exacto.
3. Conservar una copia segura de la clave mientras existan entradas cifradas.
4. Hacer revisar el aviso de privacidad y el proceso de eliminación de leads.

## Video

El MP4, el poster y los subtítulos finales viven en `public/media/`. Para regenerarlos a partir de las escenas y narraciones:

```sh
pnpm video:build
```

El video dura aproximadamente 41 segundos, se carga bajo demanda (`preload="none"`) e incluye subtítulos y transcripción en español.

## Publicación

Producción: `https://olin-credit.olin-mx.workers.dev`

El sitio se publica como activos estáticos en Cloudflare Workers. Después de iniciar sesión con Wrangler, una nueva versión se valida y publica con:

```sh
pnpm deploy
```

`pnpm deploy` crea `public/config.js` desde la plantilla de producción si el
archivo no existe; si ya existe, lo conserva para permitir un dominio de API
personalizado.

También puede generar la configuración durante el despliegue sin escribirla en
el repositorio:

```sh
OLIN_DEMO_URL="https://demo.example.mx/" \
OLIN_WAITLIST_API_URL="https://api.example.mx/api/v1/waitlist" \
pnpm deploy
```

Antes de publicar públicamente:

1. Definir el dominio final en `astro.config.mjs` mediante la propiedad `site` para generar URL canónica e imagen social absolutas.
2. Inyectar `public/config.js` durante el despliegue.
3. Configurar y probar el API de lista de espera desde el dominio público.
4. Hacer validar los textos legales preliminares por asesoría mexicana.

El sitio no afirma que Olin origine crédito, garantice aprobación ni prediga incumplimiento. Los casos y datos mostrados son sintéticos.
