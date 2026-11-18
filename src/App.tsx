import { useCallback, useEffect, useState } from 'react';
import { ArrowLeft, Orbit } from 'lucide-react';
import {
  ApiError,
  createScan,
  repositoryName,
  scanFiles,
  scanGraph,
  scanSummary,
  type FileManifest,
  type ScanSummary,
} from './api';
import { loadSample, openDocument } from './data';
import { sourceIdentity, type ScanSource } from './source';
import type { AtlasGraph } from './graph/types';
import { Home } from './components/Home';
import { ScanProgress, statusLabel } from './components/ScanStatus';
import { ProjectReport, type ProjectView } from './ProjectReport';

/** The address names the report: ?scan=<id> or ?sample=aegra. Nothing is substituted. */
function useSearch() {
  const [search, setSearch] = useState(window.location.search);
  useEffect(() => {
    const sync = () => setSearch(window.location.search);
    window.addEventListener('popstate', sync);
    return () => window.removeEventListener('popstate', sync);
  }, []);
  const open = useCallback((next: string) => {
    window.history.pushState(null, '', next || window.location.pathname);
    setSearch(next);
  }, []);
  return [search, open] as const;
}

export default function App() {
  const [search, open] = useSearch();
  const params = new URLSearchParams(search);
  const scanId = params.get('scan');
  const home = () => open('');
  if (scanId) return <ApiScan key={scanId} id={scanId} open={open} />;
  if (params.get('sample') === 'aegra') return <SampleScan onHome={home} />;
  return <Home open={open} />;
}

function Message({
  title,
  detail,
  onHome,
  onRetry,
}: {
  title: string;
  detail?: string | null;
  onHome?: () => void;
  onRetry?: () => void;
}) {
  return (
    <main className="scan-loading" role="status">
      <Orbit size={32} />
      <h1>{title}</h1>
      {detail && <p>{detail}</p>}
      {(onHome || onRetry) && (
        <div className="progress-actions">
          {onHome && (
            <button className="secondary-button" onClick={onHome}>
              <ArrowLeft size={14} /> All scans
            </button>
          )}
          {onRetry && (
            <button className="secondary-button" onClick={onRetry}>
              Try again
            </button>
          )}
        </div>
      )}
    </main>
  );
}

function SampleScan({ onHome }: { onHome: () => void }) {
  const [graph, setGraph] = useState<AtlasGraph | null>(null),
    [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    loadSample(controller.signal)
      .then(setGraph)
      .catch((error: Error) => {
        if (!controller.signal.aborted) setError(error.message);
      });
    return () => controller.abort();
  }, []);
  if (!graph)
    return (
      <Message
        title={
          error ? 'The scan could not be opened.' : 'Opening the Aegra network…'
        }
        detail={error || 'Loading recorded code and source evidence.'}
        onHome={error ? onHome : undefined}
        onRetry={error ? () => window.location.reload() : undefined}
      />
    );
  return (
    <AtlasWorkspace graph={graph} source={{ kind: 'sample' }} onHome={onHome} />
  );
}

function ApiScan({ id, open }: { id: string; open: (search: string) => void }) {
  const [scan, setScan] = useState<ScanSummary | null>(null),
    [graph, setGraph] = useState<AtlasGraph | null>(null),
    [error, setError] = useState<ApiError | null>(null),
    [graphError, setGraphError] = useState<string | null>(null),
    [retryError, setRetryError] = useState<string | null>(null),
    [attempt, setAttempt] = useState(0);
  // Poll the graph-free summary while this process still works on the scan.
  useEffect(() => {
    const controller = new AbortController();
    let timer: number | undefined;
    async function poll() {
      try {
        const next = await scanSummary(id, controller.signal);
        setScan(next);
        setError(null);
        if (next.inProgress)
          timer = window.setTimeout(poll, next.hasGraph ? 4000 : 2000);
      } catch (caught) {
        if (controller.signal.aborted) return;
        const failure =
          caught instanceof ApiError
            ? caught
            : new ApiError('The scan could not be loaded.', 0);
        setError(failure);
        if (failure.status !== 404) timer = window.setTimeout(poll, 5000);
      }
    }
    poll();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [id, attempt]);
  const hasGraph = !!scan?.hasGraph;
  useEffect(() => {
    if (!hasGraph) return;
    const controller = new AbortController();
    setGraphError(null);
    scanGraph(id, controller.signal)
      .then((document) => setGraph(openDocument(document)))
      .catch((caught: Error) => {
        if (!controller.signal.aborted) setGraphError(caught.message);
      });
    return () => controller.abort();
  }, [id, hasGraph, attempt]);
  const [manifest, setManifest] = useState<FileManifest | null>(null);
  const hasFiles = !!scan?.hasFiles;
  useEffect(() => {
    if (!hasFiles) return;
    const controller = new AbortController();
    // The tree is context; without it the rail falls back to files the graph names.
    scanFiles(id, controller.signal)
      .then(setManifest)
      .catch(() => undefined);
    return () => controller.abort();
  }, [id, hasFiles]);
  const home = () => open('');
  async function retry() {
    if (!scan) return;
    setRetryError(null);
    try {
      const created = await createScan({
        repositoryUrl: scan.repositoryUrl,
        ...(scan.revision ? { revision: scan.revision } : {}),
        model: scan.model,
        agentCount: scan.agentCount,
        agreementThreshold: scan.agreementThreshold,
      });
      open(`?scan=${created.id}`);
    } catch (caught) {
      setRetryError((caught as Error).message);
    }
  }
  if (!scan)
    return error ? (
      <Message
        title={
          error.status === 404
            ? 'This scan does not exist on the scan service.'
            : 'The scan could not be opened.'
        }
        detail={
          error.status === 404
            ? `No saved scan has the ID ${id}. It may belong to another scan service or data directory.`
            : error.message
        }
        onHome={home}
        onRetry={
          error.status === 404 ? undefined : () => setAttempt(attempt + 1)
        }
      />
    ) : (
      <Message title="Opening the scan…" />
    );
  if (graphError)
    return (
      <Message
        title={`${repositoryName(scan.repositoryUrl)} has no graph to show.`}
        detail={`${graphError} Status: ${statusLabel(scan)}.`}
        onHome={home}
        onRetry={() => setAttempt(attempt + 1)}
      />
    );
  if (!scan.hasGraph)
    return (
      <ScanProgress
        scan={scan}
        onHome={home}
        onRetry={retry}
        retryError={retryError}
      />
    );
  if (!graph)
    return (
      <Message
        title={`Opening the ${repositoryName(scan.repositoryUrl)} network…`}
        detail="Loading recorded code and source evidence."
      />
    );
  return (
    <AtlasWorkspace
      graph={graph}
      source={{ kind: 'api', scan }}
      manifest={manifest}
      onHome={home}
      connectionError={error?.message}
    />
  );
}
function AtlasWorkspace({
  graph,
  source,
  manifest,
  onHome,
  connectionError,
}: {
  graph: AtlasGraph;
  source: ScanSource;
  manifest?: FileManifest | null;
  onHome: () => void;
  connectionError?: string;
}) {
  const [search, open] = useSearch();
  const address = new URLSearchParams(search);
  const requested = address.get('view');
  const view: ProjectView =
    requested === 'cinematic'
      ? '3d'
      : requested === 'routes' || requested === 'issues' || requested === '3d'
        ? requested
        : '2d';
  function changeView(next: ProjectView) {
    address.set('view', next === '3d' ? 'cinematic' : next);
    open(`?${address}`);
  }
  return (
    <main className="atlas-app">
      <header className="app-header">
        <button className="secondary-button" onClick={onHome}>
          <ArrowLeft size={14} /> All scans
        </button>
        <strong>{sourceIdentity(source).name}</strong>
        {source.kind === 'sample' && <small>Sample project</small>}
        {connectionError && <span role="status">{connectionError}</span>}
        {(['3d', '2d', 'routes', 'issues'] as const).map((tab) => (
          <button
            key={tab}
            className="secondary-button"
            aria-pressed={tab === view}
            onClick={() => changeView(tab)}
          >
            {tab.toUpperCase()}
          </button>
        ))}
      </header>
      <ProjectReport
        graph={graph}
        source={source}
        manifest={manifest}
        view={view}
        onViewChange={changeView}
      />
    </main>
  );
}
