/** Material Symbols Outlined icon, as used throughout the Stitch designs. */
export function Icon({ name, size, className = "" }: { name: string; size?: number; className?: string }) {
  const sizeStyle = size ? { fontSize: `${size}px` } : undefined;
  return (
    <span className={`material-symbols-outlined ${className}`} style={sizeStyle} aria-hidden="true">
      {name}
    </span>
  );
}
