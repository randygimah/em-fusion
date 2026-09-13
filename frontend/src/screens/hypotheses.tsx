/**
 * The Hypotheses destination. spec: nav-001 (second decision).
 *
 * Not the Hypotheses screen — that is `hyp-*`, and none of it is built. The
 * rail carries three entries because FR-701 fixes three, so this entry exists
 * and has to lead somewhere. It names what is missing rather than rendering a
 * blank workspace, which would read as a fault rather than as a gap.
 */
const HypothesesScreen = () => (
  <main className="min-h-screen bg-[#0b0e15] p-6 text-[#e1e2ec]">
    <h1 className="text-xl font-semibold">Hypotheses</h1>
    <p className="mt-3 max-w-[60ch] text-[14px] text-[#c2c6d6]">
      This screen is not built yet. It will hold the analyst workbench: a generated hypothesis with its supporting evidence, its
      uncertainty, the alternatives it was chosen over, and which generator produced it.
    </p>
    <p className="mt-3 max-w-[60ch] text-[14px] text-[#8c909f]">
      Nothing upstream of it exists either — no detector has been written, so there are no anomalies to bundle and nothing to explain.
    </p>
  </main>
);

export default HypothesesScreen;
