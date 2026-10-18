"use client";

import { type ReactNode, useEffect, useRef, useState } from "react";

/** Renders 1280x720 content scaled down to the available width (keeps the 16:9 box). */
export function ScaledCanvas({ width = 1280, height = 720, className = "", children }: { width?: number; height?: number; className?: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => setScale(el.clientWidth / width);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, [width]);

  return (
    <div ref={ref} className={`relative w-full overflow-hidden ${className}`} style={{ aspectRatio: `${width} / ${height}` }}>
      {scale > 0 && (
        <div className="absolute left-0 top-0 origin-top-left" style={{ width, height, transform: `scale(${scale})` }}>
          {children}
        </div>
      )}
    </div>
  );
}

/** A design variant in a sandboxed iframe (no scripts, no same-origin access). */
export function DesignFrame({ html, title }: { html: string; title: string }) {
  return <iframe title={title} srcDoc={html} sandbox="" className="w-[1280px] h-[720px] border-0 pointer-events-none bg-white" />;
}
