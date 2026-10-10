/**
 * The Hypotheses destination. spec: nav-001 (second decision), nav-004.
 *
 * Not the Hypotheses screen — that is `hyp-*`, not yet built. The rail carries
 * three entries because FR-701 fixes three, so this entry exists and has to lead
 * somewhere. It names what is missing rather than rendering a blank workspace,
 * and, opened from a card's address (nav-004), names the explanation it was
 * asked for, so the link is visibly followed.
 */
const HypothesesScreen = ({ hypothesisId = null }: { hypothesisId?: number | null }) => (
  <main className="min-h-screen bg-[#0b0e15] p-6 text-[#e1e2ec]">
    <h1 className="text-xl font-semibold">Hypotheses</h1>
    {hypothesisId !== null && <p className="mt-3 text-[14px] text-[#adc6ff]">Asked for explanation {hypothesisId}.</p>}
    <p className="mt-3 max-w-[60ch] text-[14px] text-[#c2c6d6]">
      This screen is not built yet. It will hold the analyst workbench: a generated hypothesis with its supporting evidence, its uncertainty, the
      alternatives it was chosen over, and which generator produced it.
    </p>
  </main>
);

export default HypothesesScreen;
