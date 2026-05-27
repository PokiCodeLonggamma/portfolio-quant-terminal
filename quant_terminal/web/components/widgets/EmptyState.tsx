export type EmptyStateProps = {
  title?: string;
  text?: string;
  icon?: string;
};

export function EmptyState({ title = "No data", text, icon = "📭" }: EmptyStateProps) {
  return (
    <div
      data-testid="empty-state"
      className="text-center p-7"
      style={{
        background: "var(--color-card)",
        border: "1px solid var(--color-border)",
        borderRadius: 0,
      }}
    >
      <div style={{ fontSize: "2.2rem", opacity: 0.75, marginBottom: 8 }}>{icon}</div>
      <div
        className="qt-display"
        style={{ fontWeight: 700, fontSize: "1.1rem", color: "var(--color-bone)", marginBottom: 4 }}
      >
        {title}
      </div>
      {text && (
        <div className="qt-mono text-sm" style={{ color: "var(--color-bone-muted)" }}>
          {text}
        </div>
      )}
    </div>
  );
}
