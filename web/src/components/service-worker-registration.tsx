"use client";

import { useEffect } from "react";

export function ServiceWorkerRegistration() {
  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        // Offline shell is a real feature, not a critical path — a
        // registration failure (e.g. an unsupported browser) shouldn't
        // block the app from working online.
      });
    }
  }, []);

  return null;
}
