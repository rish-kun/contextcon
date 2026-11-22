import type { Metadata } from "next";
import {
  AudienceSection,
  CtaSection,
  DiffersSection,
  FitSection,
  Hero,
  InvestorSection,
  JudgmentSection,
  LimitsSection,
  PrinciplesSection,
  ProblemSection,
  SiteFooter,
  SiteHeader,
  StatusSection,
  StepsSection,
} from "@/components/marketing/sections";

export const metadata: Metadata = {
  title: "DealProof · First-pass screening with the evidence attached",
  description:
    "DealProof finds companies that match an investment thesis, checks each claim against dated, independent evidence, and says plainly what it could not verify.",
};

/**
 * Marketing home page. Layout follows docs/design/design-direction.md section 11.1:
 * a centred serif hero that hands over to the claim ledger, then the product shown
 * working, then the argument in numbered and tabular form.
 */
export default function Home() {
  return (
    <div className="min-h-dvh bg-paper-warm text-base">
      {/* Entrances are driven by script; without it everything is simply shown. */}
      <noscript>
        <style>{`[data-reveal]{opacity:1!important;transform:none!important}[data-pending]{display:none!important}`}</style>
      </noscript>
      <SiteHeader />
      <main>
        <Hero />
        <StepsSection />
        <ProblemSection />
        <StatusSection />
        <FitSection />
        <JudgmentSection />
        <InvestorSection />
        <PrinciplesSection />
        <LimitsSection />
        <DiffersSection />
        <AudienceSection />
        <CtaSection />
      </main>
      <SiteFooter />
    </div>
  );
}
