import { redirect } from "next/navigation";

/** The showcase opens on its case. */
export default function ShowcaseIndex() {
  redirect("/showcase/case");
}
