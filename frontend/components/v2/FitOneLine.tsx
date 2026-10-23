"use client";
import { useEffect, useRef } from "react";

/** Keeps a big tile number on one line: if it is wider than its box it shrinks just enough to fit; if it fits it keeps
 *  the tile's normal size. Text that would need under 60%, or
 *  has its own fixed size (a sector name), keeps its size and wraps as before. */
export default function FitOneLine({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current, box = el?.parentElement;
    if (!el || !box) return;
    const fit = () => {
      el.style.fontSize = ""; el.style.whiteSpace = "";
      const room = box.clientWidth, need = el.scrollWidth;
      if (need <= room || need === 0) return;
      if (room / need >= 0.6) el.style.fontSize = `${room / need}em`;
      if (el.scrollWidth > room + 1) { el.style.fontSize = ""; el.style.whiteSpace = "normal"; }   // own fixed size: wrap
    };
    fit();
    document.fonts?.ready.then(fit);                  // widths change once the web font arrives
    const ro = new ResizeObserver(fit);
    ro.observe(box);
    return () => ro.disconnect();
  }, [children]);
  return <span ref={ref} className="inline-block max-w-full whitespace-nowrap align-top" data-fit>{children}</span>;
}
