"use client";

import Link from "next/link";
import { listTheses, type Schemas } from "@/lib/api/client";
import { formatDate } from "@/lib/format";
import { useLoad } from "@/lib/use-load";
import {
  Button,
  EmptyState,
  Loadable,
  Page,
  PageHeader,
  Panel,
  PanelBody,
  RowLink,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui";

const STATUS: Record<Schemas["ThesisStatus"], string> = {
  draft: "Criteria ready, not searched",
  searching: "Searching",
  ready: "Shortlist ready",
  failed: "Search stopped",
};

/**
 * `/app/discover`. Every screening in the workspace, newest first: the thesis in the
 * analyst's words, where its search stands, and how many companies it shortlisted.
 */
export function ThesisList() {
  const [state, retry] = useLoad("theses", () => listTheses(), "The screenings were not returned");
  const theses = state.status === "ready" ? state.data : null;
  const shortlisted = theses?.reduce((sum, thesis) => sum + thesis.shortlist_count, 0) ?? 0;

  const newScreening = (
    <Button asChild variant="primary">
      <Link href="/app/discover/new">New screening</Link>
    </Button>
  );

  return (
    <Page>
      <PageHeader
        title="Screenings"
        meta="A thesis, its criteria and the shortlist it produced"
        figures={
          theses && theses.length > 0
            ? [
                { label: theses.length === 1 ? "Screening" : "Screenings", value: theses.length },
                { label: "Companies shortlisted", value: shortlisted },
              ]
            : undefined
        }
        actions={newScreening}
      />

      <Panel>
        <PanelBody flush>
          <Loadable
            state={state}
            what="Screenings"
            onRetry={retry}
            loading={{ label: "Loading screenings", shape: "rows", count: 3 }}
            isEmpty={(data) => data.length === 0}
            empty={
              <EmptyState title="No screenings yet" actions={newScreening}>
                A screening starts from a thesis: what you are looking for, in plain words.
                DealProof turns it into criteria you can edit, then searches live company data
                for companies that match.
              </EmptyState>
            }
          >
            {(data) => (
              <Table density="default" flush>
                <TableHeader>
                  <TableRow>
                    <TableHead>Thesis</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead numeric>Criteria</TableHead>
                    <TableHead numeric>Shortlisted</TableHead>
                    <TableHead numeric>Started</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {[...data]
                    .sort((a, b) => b.created_at.localeCompare(a.created_at))
                    .map((thesis) => (
                      <TableRow key={thesis.id} className="relative">
                        <TableCell className="max-w-xl min-w-64">
                          <RowLink
                            stretch
                            href={`/app/discover/${encodeURIComponent(thesis.id)}`}
                            className="line-clamp-2"
                          >
                            {thesis.text}
                          </RowLink>
                        </TableCell>
                        <TableCell className="whitespace-nowrap">{STATUS[thesis.status]}</TableCell>
                        <TableCell numeric>{thesis.criteria_count}</TableCell>
                        <TableCell numeric>{thesis.shortlist_count}</TableCell>
                        <TableCell numeric>{formatDate(thesis.created_at)}</TableCell>
                      </TableRow>
                    ))}
                </TableBody>
              </Table>
            )}
          </Loadable>
        </PanelBody>
      </Panel>
    </Page>
  );
}
