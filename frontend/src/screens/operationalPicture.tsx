
import type { OperationalPicture as OperationalPictureData } from "../types/operationalPicture";

interface Props {
  operationalPicture: OperationalPictureData; //screen accepts data as a prop, which is of type OperationalPictureData
}

const OperationalPictureScreen = ({ operationalPicture }: Props) => {
  const anomalyLabel = `${operationalPicture.detectionSummary.anomalyScore}%`;
  const signalIntegrityLabel = `${operationalPicture.detectionSummary.signalIntegrity.toFixed(2)}`;
  return (
    <main className="min-h-screen bg-[#0b0e15] text-[#e1e2ec]">
      <header className="flex items-center justify-between border-b border-[#424754] bg-[#1d2027] px-6 py-4">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.05em] text-[#8c909f]">EM Fusion</p>
          <h1 className="text-xl font-semibold">{operationalPicture.scenario.name}</h1>
        </div>
        <div className="text-left font-mono text-sm">
          <p className="text-[#4cd7f6]">{operationalPicture.scenario.dataMode}</p>
        </div>
        <div className="text-right font-mono text-sm">
          <p className="text-[#4cd7f6]">{operationalPicture.scenario.health}</p>
        </div>
      </header>

      <section className="grid gap-4 p-6 lg:grid-cols-[1fr_360px]">
        <div className="min-h-[480px] border border-[#424754] bg-black p-4">
          <p className="font-mono text-xs uppercase tracking-[0.05em] text-[#8c909f]">Operational Picture</p>
          {operationalPicture.rfSensors.map((sensor) => (
            <div key={sensor.id} className="mt-4 border border-dashed border-[#df7412] p-8 text-center">
              <p className="font-mono text-sm text-[#ffb786]">{sensor.signalId} Signal Noise</p>
              <p className="mt-2 text-[#4cd7f6]">{sensor.stationName}</p>
            </div>
          ))}
        </div>

        <aside className="space-y-4">
          <section className="border border-[#424754] bg-[#1d2027] p-4">
            <h2 className="text-2xl font-semibold text-[#adc6ff]">Active Hypotheses</h2>
            {operationalPicture.hypotheses.length == 0 ? (
              <p className="mt-4 text-sm text-[#8c909f]">No active hypotheses</p>
            ) : (
              operationalPicture.hypotheses.map((hypothesis) => (
                <article key={hypothesis.id}>
                  <h3 className="mt-4 text-xl font-semibold">{hypothesis.title}</h3>
                  <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <dt className="font-mono uppercase text-[#8c909f]">Confidence</dt>
                      <dd>{hypothesis.confidence}</dd>
                    </div>
                    <div>
                      <dt className="font-mono uppercase text-[#8c909f]">Severity</dt>
                      <dd>{hypothesis.severity}</dd>
                    </div>
                    <div className="col-span-2">
                      <dt className="font-mono uppercase text-[#8c909f]">Evidence</dt>
                      <dd>{hypothesis.evidence}</dd>
                    </div>
                  </dl>
                </article>
              ))
            )}
          </section>

          <section className="border border-[#424754] bg-[#1d2027] p-4">
            <h2 className="font-mono text-sm uppercase tracking-[0.05em] text-[#c2c6d6]">Detection Summary</h2>
            <dl className="mt-4 space-y-3">
              <div className="flex justify-between">
                <dt>Anomaly Score</dt>
                <dd className="font-mono text-[#ffb786]">{anomalyLabel}</dd>
              </div>
              <div className="flex justify-between">
                <dt>Signal Integrity Score</dt>
                <dd className="font-mono text-[#4cd7f6]">{signalIntegrityLabel}</dd>
              </div>
            </dl>
          </section>
        </aside>
      </section>
    </main>
  );
};

export default OperationalPictureScreen;
