import { useEffect, useState } from "react";

export interface ThemeColors {
  bg: string;
  panel: string;
  panel2: string;
  border: string;
  fg: string;
  muted: string;
  accent: string;
  up: string;
  down: string;
  warn: string;
}

function read(): ThemeColors {
  const cs = getComputedStyle(document.documentElement);
  return {
    bg:     cs.getPropertyValue("--color-bg").trim() || "#000",
    panel:  cs.getPropertyValue("--color-panel").trim() || "#0a0a0a",
    panel2: cs.getPropertyValue("--color-panel-2").trim() || "#141414",
    border: cs.getPropertyValue("--color-border").trim() || "#2a2a2a",
    fg:     cs.getPropertyValue("--color-fg").trim() || "#fff",
    muted:  cs.getPropertyValue("--color-muted").trim() || "#999",
    accent: cs.getPropertyValue("--color-accent").trim() || "#00d9ff",
    up:     cs.getPropertyValue("--color-up").trim() || "#ff3b3b",
    down:   cs.getPropertyValue("--color-down").trim() || "#00dd55",
    warn:   cs.getPropertyValue("--color-warn").trim() || "#f59e0b",
  };
}

/** Hook returning current theme colors. Re-reads when data-theme attribute changes. */
export function useThemeColors(): ThemeColors {
  const [c, setC] = useState<ThemeColors>(() => read());
  useEffect(() => {
    const update = () => setC(read());
    update();
    const obs = new MutationObserver(update);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => obs.disconnect();
  }, []);
  return c;
}
