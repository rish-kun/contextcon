import {
  Database,
  FileCheck,
  FileText,
  Handshake,
  Landmark,
  type LucideIcon,
  Megaphone,
  Newspaper,
  Quote,
  Users,
} from "lucide-react";
import type { ClaimStatus, ReliabilityClass } from "@/lib/types";
import { Icon } from "@/components/ui/icon";

/**
 * The six claim-status glyphs. Each has its own silhouette, so the set reads in
 * greyscale, in print and for colour-blind readers:
 * solid circle, half circle, diamond, solid octagon, open ring with a question mark,
 * broken ring. They draw in currentColor.
 */
interface GlyphProps {
  size?: number;
  className?: string;
}

function Svg({ size = 16, className, children }: GlyphProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden
      focusable={false}
      className={className}
    >
      {children}
    </svg>
  );
}

const knockout = {
  stroke: "var(--color-surface)",
  strokeWidth: 1.5,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

const line = {
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

function SupportedGlyph(props: GlyphProps) {
  return (
    <Svg {...props}>
      <circle cx="8" cy="8" r="7" fill="currentColor" />
      <path d="M4.9 8.3 7 10.4l4.1-4.6" {...knockout} />
    </Svg>
  );
}

function ContradictedGlyph(props: GlyphProps) {
  return (
    <Svg {...props}>
      <path d="M5.1 1h5.8L15 5.1v5.8L10.9 15H5.1L1 10.9V5.1z" fill="currentColor" />
      <path d="m5.8 5.8 4.4 4.4m0-4.4-4.4 4.4" {...knockout} />
    </Svg>
  );
}

function PartialGlyph(props: GlyphProps) {
  return (
    <Svg {...props}>
      <circle cx="8" cy="8" r="6.25" {...line} />
      <path d="M8 1.75a6.25 6.25 0 0 0 0 12.5z" fill="currentColor" />
    </Svg>
  );
}

function ConflictingGlyph(props: GlyphProps) {
  return (
    <Svg {...props}>
      <path d="M8 1.2 14.8 8 8 14.8 1.2 8z" {...line} />
      <path
        d="M5.4 8h5.2M6.6 6.8 5.4 8l1.2 1.2m2.8-2.4L10.6 8 9.4 9.2"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

function CannotVerifyGlyph(props: GlyphProps) {
  return (
    <Svg {...props}>
      <circle cx="8" cy="8" r="6.25" {...line} />
      <path d="M6.3 6.4a1.75 1.75 0 1 1 2.6 1.5c-.6.35-.9.7-.9 1.3" {...line} />
      <circle cx="8" cy="11.3" r="0.85" fill="currentColor" />
    </Svg>
  );
}

function NotCheckedGlyph(props: GlyphProps) {
  return (
    <Svg {...props}>
      <circle cx="8" cy="8" r="6.25" {...line} strokeLinecap="butt" strokeDasharray="2.6 2.31" />
    </Svg>
  );
}

/** An open ring: a check that has not settled yet, or a step that has not started. */
export function PendingGlyph(props: GlyphProps) {
  return (
    <Svg {...props}>
      <circle cx="8" cy="8" r="6.25" stroke="currentColor" strokeWidth="1.5" />
    </Svg>
  );
}

const STATUS_GLYPH: Record<ClaimStatus, (props: GlyphProps) => React.ReactNode> = {
  supported: SupportedGlyph,
  partially_corroborated: PartialGlyph,
  conflicting_evidence: ConflictingGlyph,
  contradicted: ContradictedGlyph,
  cannot_verify: CannotVerifyGlyph,
  not_checked: NotCheckedGlyph,
};

export function StatusGlyph({ status, ...props }: GlyphProps & { status: ClaimStatus }) {
  const Glyph = STATUS_GLYPH[status];
  return <Glyph {...props} />;
}

/** One glyph per reliability class, 14px inside a source chip. */
const SOURCE_CLASS_ICON: Record<ReliabilityClass, LucideIcon> = {
  registry: Landmark,
  audited_statement: FileCheck,
  counterparty_confirmation: Handshake,
  company_announcement: Megaphone,
  professional_profile_signal: Users,
  news: Newspaper,
  seller_document: FileText,
  seller_statement: Quote,
  data_provider: Database,
};

export function SourceClassGlyph({
  reliability,
  size = 14,
  className,
}: {
  reliability: ReliabilityClass;
  size?: number;
  className?: string;
}) {
  return <Icon icon={SOURCE_CLASS_ICON[reliability]} size={size} className={className} />;
}
