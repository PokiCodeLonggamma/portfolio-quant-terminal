import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export type PlaceholderPanelProps = {
  title: string;
  description?: string;
  endpoints?: string[];
  phase?: string;
};

export function PlaceholderPanel({
  title,
  description,
  endpoints,
  phase = "Phase 5",
}: PlaceholderPanelProps) {
  return (
    <Card style={{ borderLeftColor: "var(--color-amber)" }}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {description && (
          <p className="qt-mono text-sm mb-3" style={{ color: "var(--color-bone-muted)" }}>
            {description}
          </p>
        )}
        <div
          className="qt-mono text-[0.65rem] uppercase mb-2"
          style={{ letterSpacing: "0.12em", color: "var(--color-bone-dim)" }}
        >
          Wired in {phase}
        </div>
        {endpoints && endpoints.length > 0 && (
          <ul className="qt-mono text-xs" style={{ color: "var(--color-bone-muted)" }}>
            {endpoints.map((e) => (
              <li key={e}>
                <span style={{ color: "var(--color-rule)" }}>→</span>{" "}
                <code style={{ color: "var(--color-bone)" }}>{e}</code>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
