import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Practice Forge",
    short_name: "Practice Forge",
    description:
      "Ingest a textbook once. Generate original, execution-verified practice problem sets in minutes, forever.",
    start_url: "/",
    display: "standalone",
    background_color: "#fdf8f6",
    theme_color: "#6b2737",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      {
        src: "/icons/icon-512-maskable.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
