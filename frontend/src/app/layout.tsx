import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/components/providers";
import { AssistantWidget } from "@/components/assistant/AssistantWidget";
import { Suspense } from "react";

export const metadata: Metadata = {
  title: "AI Quality Assurance Command Center",
  description: "AI Agent–based End-to-End Software Test Life Cycle Automation",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="font-sans antialiased">
        <Providers>
          {children}
          <Suspense fallback={null}>
            <AssistantWidget />
          </Suspense>
        </Providers>
      </body>
    </html>
  );
}

