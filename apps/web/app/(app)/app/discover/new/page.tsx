import type { Metadata } from "next";
import { NewThesis } from "@/components/discover/new-thesis";

export const metadata: Metadata = { title: "New thesis" };

export default function NewThesisPage() {
  return <NewThesis />;
}
