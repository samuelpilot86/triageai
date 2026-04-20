import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "trIAge — How it's built",
  description:
    "Architecture, model routing, and integration decisions behind trIAge.",
};

export default function AboutLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
