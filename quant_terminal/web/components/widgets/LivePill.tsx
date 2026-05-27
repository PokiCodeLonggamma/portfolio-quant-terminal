type Status = "live" | "polling" | "offline";

export function LivePill({ status, label }: { status: Status; label?: string }) {
  const color =
    status === "live" ? "var(--color-mint)" :
    status === "polling" ? "var(--color-amber)" :
    "var(--color-mercury)";
  const text = label ?? (status === "live" ? "LIVE" : status === "polling" ? "POLL" : "OFFLINE");
  return (
    <span
      className="qt-mono inline-flex items-center gap-1.5"
      style={{
        padding: "3px 8px",
        border: `1px solid ${color}`,
        color,
        fontSize: "0.65rem",
        textTransform: "uppercase",
        letterSpacing: "0.12em",
        background: "var(--color-card)",
      }}
    >
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: color }} />
      {text}
    </span>
  );
}
