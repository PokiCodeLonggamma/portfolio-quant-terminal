"use client";
import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { useLogin } from "@/lib/auth";

function LoginForm() {
  const router = useRouter();
  const search = useSearchParams();
  const next = search.get("next") || "/";
  const login = useLogin();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        login.mutate(
          { email, password },
          { onSuccess: () => router.push(next) },
        );
      }}
    >
      <div className="mb-4">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="username"
          required
        />
      </div>
      <div className="mb-5">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
        />
      </div>
      {login.error && (
        <div
          className="qt-mono text-xs mb-4 p-2"
          style={{
            color: "var(--color-mercury)",
            border: "1px solid var(--color-mercury)",
            background: "var(--color-card)",
          }}
        >
          {login.error.message}
        </div>
      )}
      <Button type="submit" disabled={login.isPending} className="w-full">
        {login.isPending ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <main
      className="min-h-screen flex items-center justify-center"
      style={{ background: "var(--color-ink)" }}
    >
      <Card style={{ width: 380, padding: 0, borderLeftColor: "var(--color-rule)" }}>
        <div style={{ padding: "28px 28px 20px" }}>
          <div className="flex items-baseline gap-2 mb-1">
            <span
              className="qt-display"
              style={{
                fontVariationSettings: '"opsz" 96',
                fontWeight: 900,
                fontSize: "2rem",
                color: "var(--color-rule)",
                lineHeight: 0.9,
              }}
            >
              §
            </span>
            <h1 className="qt-display" style={{ fontSize: "1.6rem", fontWeight: 700 }}>
              Quant Terminal
            </h1>
          </div>
          <p
            className="qt-mono text-[0.7rem] uppercase mb-6"
            style={{ letterSpacing: "0.12em", color: "var(--color-bone-muted)" }}
          >
            sign in to continue
          </p>
          <Suspense fallback={<div className="qt-mono text-sm">Loading…</div>}>
            <LoginForm />
          </Suspense>
        </div>
      </Card>
    </main>
  );
}
