import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DealProof",
  description:
    "Discover opportunities. Verify the evidence. Evaluate with confidence.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
