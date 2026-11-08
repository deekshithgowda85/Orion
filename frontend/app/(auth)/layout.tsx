export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 px-4 py-10">
      <div className="text-center">
        <p className="font-mono text-[11px] uppercase tracking-[0.3em] text-muted-foreground">
          Autonomous
        </p>
        <h1 className="font-heading text-3xl font-bold">Orion</h1>
      </div>
      {children}
    </main>
  );
}
