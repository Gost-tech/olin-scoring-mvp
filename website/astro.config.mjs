import { defineConfig } from "astro/config";
import react from "@astrojs/react";

export default defineConfig({
  site: "https://olin-credit.olin-mx.workers.dev",
  integrations: [react()],
  output: "static",
  trailingSlash: "always",
  build: {
    assets: "assets",
    inlineStylesheets: "auto"
  },
  vite: {
    build: {
      cssMinify: "lightningcss"
    }
  }
});
