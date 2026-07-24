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

Esto comprueba tipos, genera las 12 rutas estáticas y valida enlaces, recursos, estructura de títulos y archivos de video.

## Configuración del demo

`public/config.js` no se versiona. Debe existir en cada entorno:

```js
const OLIN_DEMO_URL = "https://demo.ejemplo.mx";
```

En una página pública HTTPS, Olin rechaza como destino una URL local o sin HTTPS. Si no hay URL válida, los botones llevan al caso ilustrativo dentro del sitio.

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

Antes de publicar públicamente:

1. Definir el dominio final en `astro.config.mjs` mediante la propiedad `site` para generar URL canónica e imagen social absolutas.
2. Inyectar `public/config.js` durante el despliegue.
3. Conectar el CTA a un canal real de contacto o agenda.
4. Hacer validar los textos legales preliminares por asesoría mexicana.

El sitio no afirma que Olin origine crédito, garantice aprobación ni prediga incumplimiento. Los casos y datos mostrados son sintéticos.
