"use client";

// Minimum viable auth (docs/adr/0010 on the API side): a per-faculty
// bearer token, no login form, no password. A faculty member pastes
// their token once (handed to them out of band by an admin — no signup
// flow exists yet) and it's kept in localStorage from then on.

import { createContext, useContext, useSyncExternalStore, type ReactNode } from "react";

const STORAGE_KEY = "practice-forge:faculty-token";

function subscribe(callback: () => void): () => void {
  window.addEventListener("storage", callback);
  return () => window.removeEventListener("storage", callback);
}

function getSnapshot(): string | null {
  return window.localStorage.getItem(STORAGE_KEY);
}

function getServerSnapshot(): string | null {
  return null;
}

interface AuthContextValue {
  token: string | null;
  setToken: (token: string | null) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  // useSyncExternalStore, not useState+useEffect: localStorage is a real
  // external store, this is what it's for — SSR-safe (getServerSnapshot
  // matches the null the server rendered) with no synchronous setState
  // inside an effect, and it picks up changes made in OTHER tabs for free.
  const token = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  function setToken(next: string | null) {
    if (next) {
      window.localStorage.setItem(STORAGE_KEY, next);
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
    // The native "storage" event only fires in OTHER tabs, never the one
    // that made the write — dispatch one locally so this tab's own
    // useSyncExternalStore subscribers re-read the new value immediately.
    window.dispatchEvent(new Event("storage"));
  }

  return <AuthContext.Provider value={{ token, setToken }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
