/**
 * The run activity event, from the API's generated types (`lib/api/schema.ts`). The
 * contract is `docs/design/iterations/D-live-run-experience.md` §2.
 *
 * An activity is a fact about what a run did. The stream holds public lookup information
 * and the user's own criteria only: never claim text, document text or model output.
 */
import type { components } from "../api/schema";

type S = components["schemas"];

export type ActivityKind = S["ActivityKind"];
export type ActivitySubject = S["ActivitySubject"];
/** A public page or a Crustdata record. Never an uploaded document's content. */
export type ActivitySource = S["SourceRefOut"];
/** One external call, in its final state. */
export type ActivityCall = S["CallInfoOut"];
export type MarkState = "pending" | "found" | "none" | "not_checked";

type TypedItem = NonNullable<S["ActivityOut"]["items"]>[number];
type KeysOf<T> = T extends unknown ? keyof T : never;
type ValueOf<T, K> = T extends unknown ? (K extends keyof T ? T[K] : never) : never;

/**
 * A preview row inside a `finding`. The API types each row by `subject`; later stages
 * send only the fields that changed, and rows are merged by id, so the client reads them
 * as one shape with every field past `id` and `stage` optional.
 */
export type ActivityItem = { id: string; stage: string } & {
  [K in Exclude<KeysOf<TypedItem>, "id" | "stage">]?: ValueOf<TypedItem, K> | null;
};

export type Activity = Omit<S["ActivityOut"], "items"> & { items: ActivityItem[] | null };

/** `GET /runs/{id}/activity`, without the server's summary: the client adds events up itself. */
export interface ActivityPage {
  items: Activity[];
  next_after: number | null;
}
