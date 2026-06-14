import { useSyncExternalStore } from "react";

const listeners = new Set<() => void>();
const emit = () => listeners.forEach(l => l());

/** Client-side navigation — pushes history and re-renders without a full page reload. */
export function navigate(to: string) {
  if (to === window.location.pathname + window.location.search) return;
  window.history.pushState({}, "", to);
  window.scrollTo(0, 0);
  emit();
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  window.addEventListener("popstate", cb);
  return () => { listeners.delete(cb); window.removeEventListener("popstate", cb); };
}

/** Current pathname, re-rendering on pushState/popstate. */
export function usePath(): string {
  return useSyncExternalStore(subscribe, () => window.location.pathname);
}
