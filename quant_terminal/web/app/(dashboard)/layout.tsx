import { AppShell } from "@/components/shell/AppShell";
import { Providers } from "@/components/shell/Providers";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <Providers>
      <AppShell>{children}</AppShell>
    </Providers>
  );
}
