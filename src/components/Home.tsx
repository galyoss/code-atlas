import { useEffect, useState, type FormEvent } from 'react';
import { ArrowRight, ChevronRight, Orbit, Play } from 'lucide-react';
import {
  ApiError,
  createScan,
  listScans,
  repositoryName,
  reviewStatus,
  type ReviewStatus,
  type ScanSummary,
} from '../api';
import { sample } from '../data';
import { statusLabel } from './ScanStatus';

const MODEL_KEY = 'codeatlas.model';
function storedModel() {
  try {
    return localStorage.getItem(MODEL_KEY) || '';
  } catch {
    return '';
  }
}

export function Home({ open }: { open: (search: string) => void }) {
  const [scans, setScans] = useState<ScanSummary[] | null>(null),
    [listError, setListError] = useState<string | null>(null),
    [review, setReview] = useState<ReviewStatus | null>(null);
  const [repositoryUrl, setRepositoryUrl] = useState(''),
    [revision, setRevision] = useState(''),
    [model, setModel] = useState(storedModel),
    [agentCount, setAgentCount] = useState(2),
    [agreementThreshold, setAgreementThreshold] = useState(2);
  const [submitting, setSubmitting] = useState(false),
    [submitError, setSubmitError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    listScans(controller.signal)
      .then(setScans)
      .catch((error: Error) => {
        if (!controller.signal.aborted) setListError(error.message);
      });
    reviewStatus(controller.signal)
      .then(setReview)
      .catch(() => undefined);
    return () => controller.abort();
  }, []);
  const thresholdInvalid = agreementThreshold > agentCount;
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (thresholdInvalid || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const created = await createScan({
        repositoryUrl: repositoryUrl.trim(),
        ...(revision.trim() ? { revision: revision.trim() } : {}),
        model: model.trim(),
        agentCount,
        agreementThreshold,
      });
      try {
        localStorage.setItem(MODEL_KEY, model.trim());
      } catch {
        // Remembering the model is a convenience only.
      }
      open(`?scan=${created.id}`);
    } catch (error) {
      setSubmitError(
        error instanceof ApiError
          ? error.message
          : 'The scan could not be started.',
      );
      setSubmitting(false);
    }
  }
  return (
    <main className="home">
      <header className="app-header">
        <span className="brand">
          <Orbit size={23} strokeWidth={1.4} />
          <span>CodeAtlas</span>
        </span>
      </header>
      <div className="home-body">
        <form className="home-card scan-form" onSubmit={submit}>
          <div className="eyebrow">New scan</div>
          <h1>Scan a GitHub repository</h1>
          <label className="field">
            <span>Repository URL</span>
            <input
              className="input"
              required
              type="url"
              inputMode="url"
              placeholder="https://github.com/owner/repository"
              value={repositoryUrl}
              onChange={(event) => setRepositoryUrl(event.target.value)}
            />
          </label>
          <label className="field">
            <span>
              Revision <small>optional</small>
            </span>
            <input
              className="input"
              placeholder="Default branch"
              value={revision}
              onChange={(event) => setRevision(event.target.value)}
            />
            <small>
              Branch, tag or commit SHA. The scan pins the commit it resolves.
            </small>
          </label>
          <label className="field">
            <span>Review model</span>
            <input
              className="input"
              required
              placeholder="Chat Completions model, e.g. gpt-4.1"
              value={model}
              onChange={(event) => setModel(event.target.value)}
            />
            <small>
              Must support Chat Completions JSON mode on the provider configured
              for the scan service.
            </small>
          </label>
          <details className="advanced">
            <summary>
              Review options{' '}
              <span>
                {agentCount} agents · {agreementThreshold} must agree
              </span>
            </summary>
            <div className="advanced-grid">
              <label className="field">
                <span>Reviewing agents</span>
                <input
                  className="input"
                  type="number"
                  min={1}
                  max={8}
                  value={agentCount}
                  onChange={(event) =>
                    setAgentCount(Math.max(1, Number(event.target.value) || 1))
                  }
                />
              </label>
              <label className="field">
                <span>Agreement threshold</span>
                <input
                  className="input"
                  type="number"
                  min={1}
                  max={agentCount}
                  value={agreementThreshold}
                  aria-invalid={thresholdInvalid}
                  onChange={(event) =>
                    setAgreementThreshold(
                      Math.max(1, Number(event.target.value) || 1),
                    )
                  }
                />
              </label>
            </div>
            {thresholdInvalid && (
              <p className="field-error" role="alert">
                The threshold can't be higher than the number of agents, or no
                finding could ever reach agreement.
              </p>
            )}
            <small>
              Agents alternate hunter and skeptic. A finding needs this many
              agents to cite the same data access.
            </small>
          </details>
          <div className="scan-disclosure">
            {review && !review.configured ? (
              <p className="notice is-warning">
                {review.detail} The scan will still build the code graph, but
                every review vote will be inconclusive. Set{' '}
                <code>OPENAI_API_KEY</code> for the scan service to enable
                review.
              </p>
            ) : null}
            <p>
              Route slices and source excerpts are sent to the model provider.
              Each route makes {agentCount} model{' '}
              {agentCount === 1 ? 'call' : 'calls'} per check.
            </p>
          </div>
          {submitError && (
            <p className="notice is-error" role="alert">
              {submitError}
            </p>
          )}
          <button
            className="primary-button run-scan"
            type="submit"
            disabled={submitting || thresholdInvalid}
          >
            <Play size={14} />
            {submitting ? 'Checking repository…' : 'Run scan'}
          </button>
        </form>
        <section
          className="home-card saved-scans"
          aria-labelledby="saved-title"
        >
          <div className="eyebrow">Saved scans</div>
          <h2 id="saved-title">Open a report</h2>
          {listError ? (
            <p className="notice is-error">{listError}</p>
          ) : !scans ? (
            <p className="muted-copy" role="status">
              Loading saved scans…
            </p>
          ) : !scans.length ? (
            <p className="muted-copy">No scans yet. Results appear here.</p>
          ) : (
            <ul className="scan-list">
              {scans.map((scan) => (
                <li key={scan.id}>
                  <a
                    href={`?scan=${scan.id}`}
                    onClick={(event) => {
                      event.preventDefault();
                      open(`?scan=${scan.id}`);
                    }}
                  >
                    <span className="scan-row-main">
                      <strong>{repositoryName(scan.repositoryUrl)}</strong>
                      <small>
                        {scan.revision || 'default'} ·{' '}
                        {scan.resolvedRevision.slice(0, 7)}
                        {scan.createdAt &&
                          ` · ${new Date(scan.createdAt).toLocaleString()}`}
                      </small>
                    </span>
                    <span className={`status-pill ${scan.status}`}>
                      {statusLabel(scan)}
                    </span>
                    {scan.findings.length > 0 && (
                      <span className="finding-count">
                        {scan.findings.length}{' '}
                        {scan.findings.length === 1 ? 'finding' : 'findings'}
                      </span>
                    )}
                    <ChevronRight size={15} />
                  </a>
                </li>
              ))}
            </ul>
          )}
          <a
            className="sample-link"
            href="?sample=aegra"
            onClick={(event) => {
              event.preventDefault();
              open('?sample=aegra');
            }}
          >
            <span>
              <strong>
                Sample: {sample.name} {sample.tag}
              </strong>
              <small>Bundled code graph · no review agents ran</small>
            </span>
            <ArrowRight size={15} />
          </a>
        </section>
      </div>
    </main>
  );
}
