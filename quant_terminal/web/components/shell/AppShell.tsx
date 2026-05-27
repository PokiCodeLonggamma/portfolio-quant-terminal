import { ReactNode } from "react";

import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex" style={{ minHeight: "100vh" }}>
      <Sidebar />
      <div className="flex-1 flex flex-col">
        <TopBar />
        <main className="flex-1 overflow-auto" style={{ background: "var(--color-ink)" }}>
          {children}
        </main>
      </div>
    </div>
  );
}
