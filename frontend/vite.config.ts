// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - TanStack devtools (dev-only, first), tanstackStart, viteReact, tailwindcss, tsConfigPaths,
//     nitro (build-only using cloudflare as a default target), VITE_* env injection, @ path alias,
//     React/TanStack dedupe, error logger plugins, and sandbox detection (port/host/strictPort).
// Never set ssr.external or resolve.external: the Worker has no runtime module resolution, so
// the build fails. Never add compression (compressPublicAssets, vite-plugin-compression):
// hosting already compresses at the edge.
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

// `npm run build:static` (`vite build --mode static`): client-only SPA build for serving from any static file host (used by the
// Dockerfile). TanStack Start SPA mode prerenders a shell to dist/client/index.html; no Nitro/SSR server is built.
const staticBuild = process.argv.some((a, i, argv) => a === "--mode" && argv[i + 1] === "static") || process.argv.includes("--mode=static");

export default defineConfig({
  tanstackStart: {
    // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
    // nitro/vite builds from this
    server: { entry: "server" },
    ...(staticBuild ? { spa: { enabled: true, prerender: { outputPath: "/index.html" } } } : {}),
  },
  ...(staticBuild ? { nitro: false as const } : {}),
});
