export function Avatar({
  initials, variant = "user", size = 24,
}: { initials: string; variant?: "user" | "agent"; size?: number }) {
  const base = "inline-flex items-center justify-center font-mono font-bold text-white";
  const shape =
    variant === "agent"
      ? "rounded-[5px] bg-accent"
      : "rounded-full bg-[#1c1e26] border-[1.5px] border-[rgba(255,255,255,0.13)] text-text-3";
  return (
    <span className={`${base} ${shape}`} style={{ width: size, height: size, fontSize: size * 0.4 }}>
      {initials}
    </span>
  );
}
