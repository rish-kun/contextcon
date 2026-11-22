import { notFound } from "next/navigation";

/** Any unknown path under `/app` shows the in-shell "Page not found", sidebar kept. */
export default function MissingPage() {
  notFound();
}
