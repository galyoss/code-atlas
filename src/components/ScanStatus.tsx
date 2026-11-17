import { useEffect, useState } from 'react';
import { ArrowLeft, Orbit, RotateCcw } from 'lucide-react';
import { repositoryName, type ScanSummary } from '../api';

/** A queued or running scan the service no longer tracks was interrupted by a restart. */
export const interrupted = (scan: ScanSummary) =>
  (scan.status === 'queued' || scan.status === 'running') && !scan.inProgress;

export function statusLabel(scan: ScanSummary) {
  if (interrupted(scan)) return 'Interrupted';
  if (scan.reviewing) return 'Reviewing';
  return {
    queued: 'Queued',
    running: 'Scanning',
    partial: 'Partial',
    completed: 'Completed',
    failed: 'Failed',
  }[scan.status];
}

function elapsed(since: string | null, now: number) {
  if (!since) return null;
  const seconds = Math.max(0, Math.round((now - Date.parse(since)) / 1000));
  return seconds < 60
    ? `${seconds}s`
    : `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, '0')}s`;
}

const steps = [
  { key: 'queued', label: 'Queued' },
  { key: 'running', label: 'Clone and build the code graph' },
  { key: 'review', label: 'Review routes' },
] as const;

/** Shown until a graph exists. Failure and interruption keep the request visible. */
export function ScanProgress({
  scan,
  onHome,
  onRetry,
  retryError,
}: {
  scan: ScanSummary;
  onHome: () => void;
  onRetry: () => void;
  retryError: string | null;
}) {
  const [now, setNow] = useState(Date.now());
  const active = scan.inProgress && scan.status !== 'failed';
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active]);
  const current = scan.status === 'queued' ? 0 : 1;
  const stopped = scan.status === 'failed' || interrupted(scan);
  return (
    <main className="scan-loading scan-progress" aria-live="polite">
      <Orbit size={32} className={active ? 'is-spinning' : ''} />
      <div className="eyebrow">{statusLabel(scan)}</div>
      <h1>{repositoryName(scan.repositoryUrl)}</h1>
      <p className="progress-revision">
        {scan.revision || 'default branch'} ·{' '}
        <code>{scan.resolvedRevision.slice(0, 7)}</code> · {scan.model}
      </p>
      <ol className="progress-steps">
        {steps.map((step, index) => (
          <li
            key={step.key}
            className={
              index < current
                ? 'is-done'
                : index === current
                  ? stopped
                    ? 'is-stopped'
                    : 'is-active'
                  : ''
            }
          >
            <span className="step-dot" />
            {step.label}
          </li>
        ))}
      </ol>
      {scan.status === 'failed' ? (
        <p className="notice is-error" role="alert">
          {scan.error || scan.progress}
        </p>
      ) : interrupted(scan) ? (
        <p className="notice is-warning" role="alert">
          This scan stopped when the scan service restarted. No graph was
          produced. Run it again to start over with the same settings.
        </p>
      ) : (
        <p role="status">
          {scan.progress}
          {elapsed(scan.createdAt, now) &&
            ` · ${elapsed(scan.createdAt, now)} elapsed`}
        </p>
      )}
      {retryError && (
        <p className="notice is-error" role="alert">
          {retryError}
        </p>
      )}
      <div className="progress-actions">
        <button className="secondary-button" onClick={onHome}>
          <ArrowLeft size={14} /> All scans
        </button>
        {stopped && (
          <button className="primary-button" onClick={onRetry}>
            <RotateCcw size={14} /> Run again
          </button>
        )}
      </div>
    </main>
  );
}
