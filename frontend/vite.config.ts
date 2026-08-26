import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // The backend whitelists this origin for CORS; changing it means changing
    // allow_origins in app/main.py too.
    port: 5173,
    strictPort: true,
  },
});
