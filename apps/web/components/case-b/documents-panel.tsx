import type { AssessmentVersionOut, DocumentOut, RequestListOut, Schemas } from "@/lib/api/client";
import { formatDate, formatDateTime, plural } from "@/lib/format";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { DocumentDownload } from "./document-download";
import { Section, TextLink } from "./parts";

type DeletionRecord = Schemas["DeletionRecordOut"];

const KIND_LABEL: Record<DocumentOut["kind"], string> = {
  seller_deck: "Seller deck",
  seller_response: "Seller response",
  other: "Other document",
};

const ARTIFACT_LABEL: Record<string, string> = {
  document: "Uploaded file",
  extracted_text: "Extracted text",
  quote: "Stored quote",
  llm_cache: "Cached model request",
  assessment_inputs: "Assessment input snapshot",
};

function fileSize(bytes: number): string {
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1000))} KB`;
}

const REDACTED: Record<string, [one: string, many: string]> = {
  email: ["email address", "email addresses"],
  phone: ["phone number", "phone numbers"],
  pan: ["PAN", "PANs"],
  aadhaar: ["Aadhaar number", "Aadhaar numbers"],
};

function redactions(counts: Record<string, number>): string | null {
  const parts = Object.entries(counts)
    .filter(([, count]) => count > 0)
    .map(([kind, count]) => {
      const [one, many] = REDACTED[kind] ?? [kind, kind];
      return `${count} ${count === 1 ? one : many}`;
    });
  return parts.length ? `Redacted before processing: ${parts.join(", ")}` : null;
}

/** "Deleted on 22 Dec 2026 per retention". The one wording for a purged file. */
function deletedLine(date: string): string {
  return `Deleted on ${formatDate(date) ?? "an unrecorded date"} per retention`;
}

/**
 * The files on this case, each with the day it will be deleted, and the record of what
 * has already been deleted. A purged file stays in the list with its deletion date, so an
 * older assessment that cites it can say where the attachment went.
 */
export function DocumentsPanel({
  caseId,
  documents,
  deletions,
  requestList,
  versions,
}: {
  caseId: string;
  documents: DocumentOut[];
  deletions: DeletionRecord[];
  requestList: RequestListOut | null;
  versions: AssessmentVersionOut[];
}) {
  const deletionFor = (documentId: string) =>
    deletions.find((record) => record.artifact_id === documentId);
  const itemName = (id: string) => requestList?.items.find((item) => item.id === id)?.document;
  const versionFrom = (filename: string) =>
    versions.find((version) => version.trigger.includes(filename))?.version;

  return (
    <div className="flex flex-col gap-8">
      <Section
        title="Uploaded files"
        meta={documents.length}
        lead="Used only for this case. Each file, the text read from it and the quotes kept from it are deleted on the date shown."
      >
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>File</TableHead>
              <TableHead>Uploaded</TableHead>
              <TableHead>Used for</TableHead>
              <TableHead>Retention</TableHead>
              <TableHead numeric>
                <span className="sr-only">Download</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {documents.map((doc) => {
              const deletion = deletionFor(doc.id);
              const purged = doc.purged || Boolean(deletion);
              const answers = doc.answers_request_item_ids.map(itemName).filter(Boolean);
              const version = versionFrom(doc.filename);
              const redacted = redactions(doc.redaction_counts);
              return (
                <TableRow key={doc.id}>
                  <TableCell className="align-top">
                    <span className="flex flex-col gap-1">
                      <span className={purged ? "text-ink-secondary line-through" : "text-ink"}>
                        {doc.filename}
                      </span>
                      <span className="text-xs text-ink-secondary">
                        {KIND_LABEL[doc.kind]}
                        <span className="font-mono">
                          {" · "}
                          {fileSize(doc.size_bytes)}
                          {doc.pages != null ? ` · ${plural(doc.pages, "page")}` : null}
                        </span>
                      </span>
                      {redacted ? <span className="text-xs text-ink-secondary">{redacted}</span> : null}
                    </span>
                  </TableCell>
                  <TableCell className="align-top">
                    <span className="flex flex-col gap-1">
                      <span className="font-mono text-xs whitespace-nowrap text-ink">
                        {formatDateTime(doc.uploaded_at)}
                      </span>
                      <span className="text-xs text-ink-secondary">
                        {doc.uploaded_by_name ? `by ${doc.uploaded_by_name}` : "uploader not recorded"}
                      </span>
                    </span>
                  </TableCell>
                  <TableCell className="align-top">
                    <span className="flex flex-col gap-1 text-ink">
                      <span>
                        {doc.claims_extracted > 0
                          ? `${plural(doc.claims_extracted, "claim")} read from it`
                          : "No claims read from it"}
                      </span>
                      {answers.length ? (
                        <span className="text-xs text-ink-secondary">Answers: {answers.join(", ")}</span>
                      ) : null}
                      {version ? (
                        <TextLink
                          href={`/app/cases/${caseId}/assessment?v=${version}`}
                          className="text-xs"
                        >
                          View v{version} diff
                        </TextLink>
                      ) : null}
                    </span>
                  </TableCell>
                  <TableCell className="align-top">
                    {purged ? (
                      <span className="hatch inline-flex rounded-xs border border-dashed border-not-checked-line p-1">
                        <span className="rounded-xs bg-not-checked-tint px-2 py-0.5 text-xs text-not-checked">
                          {deletedLine(deletion?.deleted_at ?? doc.delete_after)}
                        </span>
                      </span>
                    ) : (
                      <span className="whitespace-nowrap text-ink">
                        Deletes on <span className="font-mono text-xs">{formatDate(doc.delete_after)}</span>
                      </span>
                    )}
                  </TableCell>
                  <TableCell numeric className="align-top font-sans">
                    {purged ? (
                      <span className="text-xs text-ink-secondary">No file to download</span>
                    ) : (
                      <DocumentDownload documentId={doc.id} filename={doc.filename} />
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Section>

      <Section
        title="Deletion record"
        meta={deletions.length}
        lead="Every deletion is written down with its date and reason, including text and quotes derived from a file."
      >
        {deletions.length === 0 ? (
          <p className="rounded-lg border border-line bg-surface px-4 py-3 text-dense text-ink-secondary">
            Nothing has been deleted from this case yet.
          </p>
        ) : (
          <ul className="flex flex-col divide-y divide-line rounded-lg border border-line bg-surface text-dense">
            {deletions.map((record) => (
              <li
                key={`${record.artifact_kind}:${record.artifact_id}`}
                className="grid gap-x-6 gap-y-1 px-4 py-3 sm:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]"
              >
                <span className="flex flex-col gap-1">
                  <span className="text-ink">
                    {record.original_filename ?? ARTIFACT_LABEL[record.artifact_kind] ?? record.artifact_kind}
                  </span>
                  <span className="text-xs text-ink-secondary">
                    {ARTIFACT_LABEL[record.artifact_kind] ?? record.artifact_kind}
                  </span>
                </span>
                <span className="flex flex-col gap-1">
                  <span className="text-ink">{deletedLine(record.deleted_at)}</span>
                  <span className="text-xs text-ink-secondary">{record.reason}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}
