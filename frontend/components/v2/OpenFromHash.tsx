"use client";
import { useEffect } from "react";

/** A link like /methodology/details#oi should land on an open fold, not a closed one. */
export default function OpenFromHash() {
  useEffect(() => {
    const open = () => {
      const el = location.hash ? document.getElementById(decodeURIComponent(location.hash.slice(1))) : null;
      if (el instanceof HTMLDetailsElement) { el.open = true; el.scrollIntoView(); }
    };
    open();
    window.addEventListener("hashchange", open);
    return () => window.removeEventListener("hashchange", open);
  }, []);
  return null;
}
