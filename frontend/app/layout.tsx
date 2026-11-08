import type { Metadata, Viewport } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "@fontsource-variable/syne";
import { MOCK_MODE } from "@/lib/mock-mode";
import { Providers } from "@/components/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Orion",
    template: "%s · Orion",
  },
  description: "Orion — live research workflow dashboard.",
  icons: {
    icon: "/orion_logo.svg",
    shortcut: "/orion_logo.svg",
  },
};

export const viewport: Viewport = {
  themeColor: "#ffffff",
  colorScheme: "light",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const page = (
    <html lang="en">
      <body className="min-h-screen font-sans antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );

  // Demo mode (dev only) runs without Clerk so the UI works with no keys.
  if (MOCK_MODE) return page;

  return (
    <ClerkProvider
      appearance={{
        variables: {
          colorPrimary: "#533afd",
          colorBackground: "#ffffff",
          colorInputBackground: "#ffffff",
          colorText: "#0d253d",
          colorTextSecondary: "#64748d",
          borderRadius: "0.5rem",
          fontFamily: "var(--font-inter), system-ui, sans-serif",
        },
      }}
    >
      {page}
    </ClerkProvider>
  );
}
