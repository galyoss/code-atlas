import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from 'react';
import {
  ArrowLeft,
  ArrowRight,
  Code2,
  Database,
  Flag,
  Orbit,
  PanelLeft,
  Search,
  X,
} from 'lucide-react';
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
import {
  indexFindings,
  nodeFindingKind,
  type FindingItem,
} from './graph/findings';
import { flowIndex } from './graph/flow';
import { ViewAnchors } from './graph/view-layout';
import { matchingSymbols } from './graph/catalog';
import type { LabelViewport } from './graph/labels';
import { initialCamera, layoutGraph } from './graph/layout';
import {
  primaryNodeAction,
  navigationVisibleIds,
  initialNavigation,
  navigate,
  type NavigationAction,
  type NavigationState,
} from './graph/navigation';
import type { AtlasGraph } from './graph/types';
import { GraphCanvas } from './components/GraphCanvas';
import { SourcePanel } from './components/SourcePanel';
import { GraphControls, type RailTab } from './components/GraphControls';
import { FindingPanel, FindingsList } from './components/FindingsPanel';
import { EndpointsList, FileTree } from './components/Navigator';
import { projectTree } from './graph/project';
import { Home } from './components/Home';
import { ScanProgress, statusLabel } from './components/ScanStatus';
import {
  accessSummary,
  dataEffect,
  effectGlyph,
  effectLabel,
} from './graph/semantics';

const CinematicGraph = lazy(() => import('./components/CinematicGraph'));

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
  manifest = null,
  onHome,
  connectionError,
}: {
  graph: AtlasGraph;
  source: ScanSource;
  manifest?: FileManifest | null;
  onHome: () => void;
  connectionError?: string;
}) {
  const [cinematic, setCinematic] = useState(() => new URLSearchParams(window.location.search).get('view') === 'cinematic');
  function changeRenderer(next: boolean) {
    const url = new URL(window.location.href);
    if (next) url.searchParams.set('view', 'cinematic');
    else url.searchParams.delete('view');
    window.history.replaceState(null, '', url);
    setCinematic(next);
    if (!next) requestAnimationFrame(() => document.querySelector<HTMLButtonElement>('.universe-launch')?.focus());
  }
  useEffect(() => {
    const sync = () => setCinematic(new URLSearchParams(window.location.search).get('view') === 'cinematic');
    window.addEventListener('popstate', sync);
    return () => window.removeEventListener('popstate', sync);
  }, []);
  const [state, dispatch] = useReducer(
    (state: NavigationState, action: NavigationAction) =>
      navigate(graph, state, action),
    undefined,
    () => initialNavigation(!window.matchMedia('(max-width: 760px)').matches),
  );
  const [panel, setPanel] = useState<'source' | 'scope' | 'finding' | null>(
      null,
    ),
    [query, setQuery] = useState(''),
    [focusedId, setFocusedId] = useState<string | null>(null);
  const scan = source.kind === 'api' ? source.scan : null;
  const [railTab, setRailTab] = useState<RailTab>(() =>
    scan?.findings.length ||
    scan?.votes.some((vote) => vote.verdict === 'present')
      ? 'findings'
      : 'endpoints',
  );
  const identity = sourceIdentity(source);
  const findings = useMemo(
    () =>
      scan
        ? indexFindings(
            graph,
            scan.findings,
            scan.votes,
            scan.agreementThreshold,
          )
        : null,
    [graph, scan],
  );
  const focused = findings?.items.find((item) => item.id === focusedId) || null;
  // The path stays emphasized while its entry flow is active; Back restores it.
  const findingPath = useMemo(
    () =>
      focused && state.flowEntry === focused.handlerId
        ? new Set(focused.path)
        : null,
    [focused, state.flowEntry],
  );
  const findingMarks = useMemo(() => {
    const marks = new Map<string, 'finding' | 'candidate'>();
    for (const [id, items] of findings?.byNode || [])
      marks.set(id, nodeFindingKind(items)!);
    return marks;
  }, [findings]);
  const findingCount =
    findings?.items.filter((item) => item.kind === 'finding').length || 0;
  const [labelViewport, setLabelViewport] = useState<LabelViewport>();
  const sourceButton = useRef<HTMLButtonElement>(null),
    scopeButton = useRef<HTMLButtonElement>(null),
    findingsButton = useRef<HTMLButtonElement>(null),
    railButton = useRef<HTMLButtonElement>(null),
    canvasArea = useRef<HTMLDivElement>(null);
  const layout = useMemo(() => layoutGraph(graph), [graph]);
  const anchors = useMemo(
    () => new ViewAnchors(graph, layout),
    [graph, layout],
  );
  const visible = useMemo(
    () => navigationVisibleIds(graph, state),
    [
      graph,
      state.expanded,
      state.collapsed,
      state.revealed,
      state.flowEntry,
      state.view,
    ],
  );
  const positions = useMemo(
    () => anchors.ensure(state.view, visible),
    [anchors, state.view, visible],
  );
  const matches = useMemo(() => matchingSymbols(graph, query), [graph, query]);
  const selected = state.selected ? graph.nodes.get(state.selected)! : null;
  const selectedAction = selected
    ? primaryNodeAction(graph, state, selected.id)
    : null;
  const flow = state.flowEntry
    ? flowIndex(graph).entries.get(state.flowEntry)!
    : null;
  const flowHandler = state.flowEntry
    ? graph.nodes.get(state.flowEntry)!
    : null;
  const selectedEffect = selected ? dataEffect(selected) : null;
  const selectedAccesses = selected ? accessSummary(selected) : null;
  const symbolsVisible = [...visible].filter(
    (id) => graph.nodes.get(id)!.canonical,
  ).length;
  const detailCount = [...visible].filter(
    (id) =>
      !graph.nodes.get(id)!.canonical && graph.nodes.get(id)!.kind !== 'group',
  ).length;
  useLayoutEffect(() => {
    const element = canvasArea.current!;
    dispatch({
      type: 'camera',
      camera: initialCamera(
        layout,
        graph,
        element.clientWidth,
        element.clientHeight,
      ),
    });
  }, [layout, graph]);
  useLayoutEffect(() => {
    const canvas = canvasArea.current!;
    const overlays = [
      ...canvas.querySelectorAll<HTMLElement>(
        '.graph-controls, .network-toolbar, .network-caption, .flow-summary, .selection-bar, .source-panel, .camera-controls, .canvas-hint, .role-captions > div',
      ),
    ];
    const measure = () => {
      const bounds = canvas.getBoundingClientRect();
      const next = {
        width: bounds.width,
        height: bounds.height,
        blocked: overlays
          .map((element) => {
            const rect = element.getBoundingClientRect();
            return {
              x: rect.left - bounds.left - 4,
              y: rect.top - bounds.top - 4,
              width: rect.width + 8,
              height: rect.height + 8,
            };
          })
          .filter((rect) => rect.width > 8 && rect.height > 8),
      };
      setLabelViewport((current) =>
        JSON.stringify(current) === JSON.stringify(next) ? current : next,
      );
    };
    measure();
    const observer = new ResizeObserver(measure);
    [canvas, ...overlays].forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, [
    panel,
    railTab,
    state.selected,
    state.flowEntry,
    state.railOpen,
    state.view,
    state.camera,
    query,
    visible,
  ]);
  const back = () => {
    setPanel(null);
    dispatch({ type: 'back' });
  };
  function centered(id: string) {
    const p = positions.get(id),
      element = canvasArea.current!;
    return p
      ? {
          ...state.camera,
          x: element.clientWidth / 2 - p.x * state.camera.scale,
          y: element.clientHeight / 2 - p.y * state.camera.scale,
        }
      : undefined;
  }
  /** Open the finding's entry flow; the cited path is emphasized within it. */
  function focusFinding(item: FindingItem | null) {
    setFocusedId(item?.id || null);
    if (item && state.flowEntry !== item.handlerId)
      dispatch({
        type: 'reveal',
        id: item.handlerId,
        camera: centered(item.handlerId),
      });
  }
  function stepTo(item: FindingItem, id: string) {
    if (state.flowEntry !== item.handlerId)
      dispatch({ type: 'reveal', id: item.handlerId });
    dispatch({ type: 'select', id });
  }
  function openFinding(item: FindingItem) {
    setPanel('finding');
    focusFinding(item);
  }
  function showRail(tab: RailTab) {
    setRailTab(tab);
    dispatch({ type: 'rail', open: true });
  }
  function openEndpoint(handlerId: string) {
    if (state.view === 'code' && state.flowEntry === handlerId) return;
    dispatch({ type: 'reveal', id: handlerId, camera: centered(handlerId) });
  }
  function openFile(groupId: string) {
    if (state.view !== 'code') dispatch({ type: 'view', view: 'code' });
    if (state.collapsed.has(groupId)) dispatch({ type: 'toggle', id: groupId });
    dispatch({ type: 'select', id: groupId });
    const region = layout.regions.get(groupId),
      element = canvasArea.current!;
    if (region)
      dispatch({
        type: 'camera',
        camera: {
          ...state.camera,
          x: element.clientWidth / 2 - region.x * state.camera.scale,
          y: element.clientHeight / 2 - region.y * state.camera.scale,
        },
      });
  }
  const tree = useMemo(
    () => projectTree(graph, manifest?.paths || null, findings),
    [graph, manifest, findings],
  );
  const selectedFindings = selected ? findings?.byNode.get(selected.id) : null;
  function findNext() {
    if (!matches.length) return;
    const index = matches.indexOf(state.selected || '');
    const id = matches[(index + 1) % matches.length],
      p = positions.get(id)!,
      element = canvasArea.current!;
    dispatch({
      type: 'reveal',
      id,
      camera: {
        ...state.camera,
        x: element.clientWidth / 2 - p.x * state.camera.scale,
        y: element.clientHeight / 2 - p.y * state.camera.scale,
      },
    });
  }
  return (
    <main
      className="atlas-app"
      data-renderer={cinematic ? 'cinematic' : '2d'}
      data-dataset={source.kind === 'sample' ? 'aegra-real' : 'scan'}
      data-finding-focus={findingPath ? focused!.id : ''}
      data-selected={state.selected || ''}
      data-scope="network"
      data-flow-entry={state.flowEntry || ''}
      data-flow-paths={JSON.stringify(flow ? [...flow.paths] : [])}
      data-flow-terminals={JSON.stringify(flow ? [...flow.terminals] : [])}
      data-view={state.view}
      data-rail-open={state.railOpen}
      data-rail-wide={state.railOpen && railTab !== 'view'}
      data-expanded={JSON.stringify([...state.expanded])}
      data-revealed={JSON.stringify([...state.revealed])}
      data-collapsed={JSON.stringify([...state.collapsed])}
      onKeyDown={(event) => {
        if (event.key === 'Escape' && !event.defaultPrevented) {
          if (panel) setPanel(null);
          else if (state.railOpen) dispatch({ type: 'rail', open: false });
          else if (query) setQuery('');
          else back();
        }
      }}
    >
      <header className="app-header" inert={cinematic} aria-hidden={cinematic}>
        <a
          className="brand"
          href={window.location.pathname}
          onClick={(event) => {
            event.preventDefault();
            onHome();
          }}
          aria-label="CodeAtlas, all scans"
        >
          <Orbit size={23} strokeWidth={1.4} />
          <span>CodeAtlas</span>
        </a>
        <span className="header-divider" />
        <span className="repository-name">
          {identity.name}
          <small>{identity.tag}</small>
        </span>
        <span className="revision" title={graph.document.repo.revision}>
          {graph.document.repo.revision.slice(0, 7)}
        </span>
        <div className="header-right">
          {scan ? (
            <>
              <span
                className={`review-state ${scan.reviewing ? 'is-reviewing' : scan.status}`}
                title={connectionError || scan.progress}
              >
                <span className="live-dot" />
                {connectionError
                  ? 'Connection lost · retrying'
                  : scan.reviewing
                    ? 'Reviewing routes…'
                    : `Review ${statusLabel(scan).toLowerCase()}`}
              </span>
              <button
                ref={findingsButton}
                className={`findings-button ${findingCount ? 'has-findings' : ''}`}
                aria-expanded={state.railOpen && railTab === 'findings'}
                aria-controls="graph-controls"
                onClick={() =>
                  state.railOpen && railTab === 'findings'
                    ? dispatch({ type: 'rail', open: false })
                    : showRail('findings')
                }
              >
                <Flag size={13} />
                {findingCount} {findingCount === 1 ? 'finding' : 'findings'}
                {findings!.items.length > findingCount && (
                  <small>
                    +{findings!.items.length - findingCount} candidates
                  </small>
                )}
              </button>
            </>
          ) : (
            <>
              <span className="live-dot" /> Sample scan · no review
            </>
          )}
        </div>
        <button className="universe-launch" aria-label="3D universe" onClick={() => changeRenderer(true)}><Orbit size={14} /><span className="universe-launch-label">3D universe</span><span className="universe-launch-short" aria-hidden="true">3D</span></button>
      </header>
      <div className="canvas-area" ref={canvasArea} inert={cinematic} aria-hidden={cinematic}>
        <GraphCanvas
          graph={graph}
          layout={layout}
          captions={anchors.captions(state.view)}
          positions={positions}
          visible={visible}
          state={state}
          dispatch={dispatch}
          matches={matches}
          searching={!!query.trim()}
          labelViewport={labelViewport}
          findingMarks={findingMarks}
          findingPath={findingPath}
        />
        {state.railOpen && (
          <GraphControls
            graph={graph}
            state={state}
            dispatch={dispatch}
            returnFocus={railButton}
            tab={railTab}
            onTab={setRailTab}
            tabs={[
              ...(findings
                ? [
                    {
                      id: 'findings' as const,
                      label: 'Findings',
                      count: findings.items.length,
                      alert: findingCount > 0,
                    },
                  ]
                : []),
              {
                id: 'endpoints',
                label: 'Endpoints',
                count: graph.document.routes.length,
              },
              {
                id: 'files',
                label: 'Files',
                count: manifest?.total ?? tree.root.fileCount,
              },
              { id: 'view', label: 'View' },
            ]}
          >
            {railTab === 'findings' && scan && findings ? (
              <FindingsList
                graph={graph}
                index={findings}
                scan={scan}
                focusedId={panel === 'finding' ? focusedId : null}
                onFocus={openFinding}
              />
            ) : railTab === 'files' ? (
              <FileTree
                tree={tree}
                total={manifest?.total ?? tree.root.fileCount}
                truncated={!!manifest?.truncated}
                onOpenFile={openFile}
                activeGroup={
                  state.selected &&
                  graph.nodes.get(state.selected)!.kind === 'group'
                    ? state.selected
                    : null
                }
              />
            ) : (
              <EndpointsList
                graph={graph}
                findings={findings}
                activeEntry={state.flowEntry}
                onOpen={(route) => openEndpoint(route.handler.symbolId)}
              />
            )}
          </GraphControls>
        )}
        <div className="network-toolbar">
          <button
            className="icon-button rail-toggle"
            ref={railButton}
            aria-label={
              state.railOpen ? 'Hide graph controls' : 'Open graph controls'
            }
            aria-controls="graph-controls"
            aria-expanded={state.railOpen}
            onClick={() => dispatch({ type: 'rail', open: !state.railOpen })}
          >
            <PanelLeft size={16} />
          </button>
          <button
            className="icon-button"
            onClick={back}
            disabled={!state.history.length}
            aria-label="Back to previous view"
            title="Back to previous view"
          >
            <ArrowLeft size={16} />
          </button>
          <div className="network-search">
            <Search size={14} />
            <input
              aria-label="Find a symbol, route or file"
              value={query}
              placeholder="Find symbol or file…"
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  findNext();
                }
              }}
            />
            {query && (
              <>
                <span role="status">
                  {matches.length ? `${matches.length} found` : 'No matches'}
                </span>
                <button onClick={() => setQuery('')} aria-label="Clear search">
                  <X size={13} />
                </button>
                <button
                  disabled={!matches.length}
                  onClick={findNext}
                  aria-label="Focus next match"
                >
                  <ArrowRight size={14} />
                </button>
              </>
            )}
          </div>
        </div>
        <div className="network-caption">
          <span>{identity.name.toUpperCase()} / CODE ATLAS</span>
          <p>
            {symbolsVisible}/{graph.baseIds.length} symbols shown <i>·</i>{' '}
            {graph.edges.filter((edge) => edge.aggregated).length} total call
            links
            {detailCount > 0 && (
              <>
                {' '}
                <i>·</i> {detailCount} detail nodes
              </>
            )}
          </p>
        </div>
        {flow && (
          <aside
            className="flow-summary"
            aria-label="Active entry flow"
            role="status"
          >
            <span className="flow-eyebrow">ENTRY → DATA</span>
            <strong>{flowHandler!.name}</strong>
            <p>
              {flow.terminals.size
                ? `${flow.terminals.size} recorded data operations · ${[...flow.terminals].filter((id) => graph.nodes.get(id)!.accesses.length).length} with named objects`
                : 'No data path recorded for this entry.'}
            </p>
            <small>
              Partial static scan ·{' '}
              {flow.paths.size &&
              [...flow.paths].some((id) => graph.nodes.get(id)!.kind === 'auth')
                ? 'includes auth context'
                : 'recorded paths only'}
            </small>
            <button
              className="icon-button"
              aria-label="Clear entry flow"
              onClick={() => {
                setPanel(null);
                dispatch({ type: 'clear-flow' });
              }}
            >
              <X size={13} />
            </button>
          </aside>
        )}
        {panel === 'finding' && focused && (
          <FindingPanel
            graph={graph}
            item={focused}
            selectedNode={state.selected}
            onStep={(id) => stepTo(focused, id)}
            onClose={() => setPanel(null)}
            returnFocus={findingsButton}
          />
        )}
        {(panel === 'source' || panel === 'scope') && (
          <SourcePanel
            graph={graph}
            source={source}
            node={selected || graph.nodes.get(graph.defaultId)!}
            mode={panel}
            onClose={() => setPanel(null)}
            returnFocus={panel === 'source' ? sourceButton : scopeButton}
          />
        )}
        {selected && (
          <section className="selection-bar" aria-label="Selected node">
            <div className="selection-copy">
              <div className="selection-heading">
                <span className={`selection-dot ${selected.kind}`} />
                <strong>{selected.name}</strong>
                {selectedEffect && (
                  <span
                    className={`effect-badge ${selectedEffect}`}
                    title={effectLabel(selectedEffect)}
                  >
                    {effectGlyph(selectedEffect)}
                  </span>
                )}
                <span className="selection-kind">
                  {selected.canonical
                    ? selected.kind === 'route'
                      ? 'handler'
                      : 'symbol'
                    : selected.kind === 'group'
                      ? 'source file'
                      : selected.kind === 'auth'
                        ? 'auth context'
                        : selected.call?.resolution === 'ambiguous'
                          ? 'unresolved call'
                          : `${selected.call?.resolution || ''} call`}
                </span>
              </div>
              <small title={selected.sourceFile || selected.range?.file}>
                {selected.sourceFile ||
                  (selected.range
                    ? `${selected.range.file}:${selected.range.startLine}–${selected.range.endLine}`
                    : selected.subtitle)}
              </small>
              {selected.groupedRoutes && (
                <div className="selection-routes">
                  {selected.groupedRoutes.map((route) => (
                    <span key={route.id}>
                      <b>{route.httpMethod}</b> {route.pathTemplate}
                    </span>
                  ))}
                </div>
              )}
              {!!selectedAccesses?.total && (
                <div className="selection-data">
                  {selected.canonical
                    ? `${selectedAccesses.read} read · ${selectedAccesses.write} write records in this body`
                    : selected.accesses
                        .map(
                          ({ access }) =>
                            `${access.operation} ${access.object.name}`,
                        )
                        .join(' · ')}
                  {selected.call && ` · ${selected.call.resolution} target`}
                </div>
              )}
            </div>
            <div className="selection-actions">
              {selectedFindings && (
                <button
                  className={`secondary-button related-findings ${nodeFindingKind(selectedFindings)}`}
                  onClick={() =>
                    selectedFindings.length === 1
                      ? openFinding(selectedFindings[0])
                      : showRail('findings')
                  }
                >
                  <Flag size={13} />
                  {selectedFindings.length}{' '}
                  {nodeFindingKind(selectedFindings) === 'finding'
                    ? selectedFindings.length === 1
                      ? 'finding'
                      : 'findings'
                    : selectedFindings.length === 1
                      ? 'candidate'
                      : 'candidates'}
                </button>
              )}
              {selected.canonical && selected.accesses.length > 0 && (
                <button
                  className="secondary-button reveal-accesses"
                  onClick={() =>
                    dispatch({ type: 'accesses', id: selected.id })
                  }
                >
                  <Database size={13} />
                  Reveal access paths
                </button>
              )}
              {selected.kind !== 'group' && (
                <button
                  ref={sourceButton}
                  className="secondary-button"
                  onClick={() => setPanel(panel === 'source' ? null : 'source')}
                  aria-expanded={panel === 'source'}
                >
                  <Code2 size={14} /> Source
                </button>
              )}
              {selected.children.length > 0 && (
                <button
                  className="primary-button"
                  onClick={() => {
                    if (selectedAction!.action.type === 'clear-flow')
                      setPanel(null);
                    dispatch(selectedAction!.action);
                  }}
                >
                  {selectedAction!.label}
                  <ArrowRight size={14} />
                </button>
              )}
              <button
                className="icon-button selection-close"
                onClick={() => {
                  setPanel(null);
                  dispatch({ type: 'select', id: null });
                }}
                aria-label="Clear selection"
              >
                <X size={14} />
              </button>
            </div>
          </section>
        )}
      </div>
      <footer className="app-footer" inert={cinematic} aria-hidden={cinematic}>
        <div className="legend" aria-label="Graph relationship legend">
          <span>
            <i className="legend-dot handler" /> Entry
          </span>
          <span>
            <i className="legend-dot symbol" /> Code symbol
          </span>
          <span>
            <i className="legend-line call" /> Calls
          </span>
          <span className="detail-legend">
            <i className="legend-line context" /> Auth / definition
          </span>
          {findingMarks.size > 0 && (
            <span>
              <i className="legend-dot finding" /> Finding
            </span>
          )}
        </div>
        <button
          ref={scopeButton}
          className="scope-button"
          onClick={() => setPanel(panel === 'scope' ? null : 'scope')}
          aria-expanded={panel === 'scope'}
        >
          <span className="partial-dot" /> Partial static scan{' '}
          <span className="scope-extra">
            · {graph.groups.length} files · scope & coverage
          </span>
        </button>
      </footer>
      {cinematic && <Suspense fallback={<div className="universe-loading" role="status">Opening the universe…</div>}><CinematicGraph graph={graph} name={identity.name} tag={identity.tag} onExit={() => changeRenderer(false)} /></Suspense>}
    </main>
  );
}
