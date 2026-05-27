import { Providers } from "@/components/shell/Providers";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  // Auth pages get the providers but NOT the AppShell.
  return <Providers>{children}</Providers>;
}
