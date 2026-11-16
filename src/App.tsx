import {
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
  Orbit,
  PanelLeft,
  Search,
  X,
} from 'lucide-react';
import { loadScan, scan } from './data';
import { flowIndex } from './graph/flow';
import { ViewAnchors } from './graph/view-layout';
import { matchingSymbols } from './graph/catalog';
import type { LabelViewport } from './graph/labels';
import { initialCamera, layoutGraph } from './graph/layout';
import {
  branchActionLabel,
  navigationVisibleIds,
  initialNavigation,
  navigate,
  type NavigationAction,
  type NavigationState,
} from './graph/navigation';
import type { AtlasGraph } from './graph/types';
import { GraphCanvas } from './components/GraphCanvas';
import { SourcePanel } from './components/SourcePanel';
import { GraphControls } from './components/GraphControls';
import {
  accessSummary,
  dataEffect,
  effectGlyph,
  effectLabel,
} from './graph/semantics';

export default function App() {
  const [graph, setGraph] = useState<AtlasGraph | null>(null),
    [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    loadScan(controller.signal)
      .then(setGraph)
      .catch((error: Error) => {
        if (!controller.signal.aborted) setError(error.message);
      });
    return () => controller.abort();
  }, []);
  if (!graph)
    return (
      <main className="scan-loading" role="status">
        <Orbit size={32} />
        <h1>
          {error
            ? 'The scan could not be opened.'
            : 'Opening the Aegra network…'}
        </h1>
        <p>{error || 'Loading recorded code and source evidence.'}</p>
        {error && (
          <button
            className="secondary-button"
            onClick={() => window.location.reload()}
          >
            Try again
          </button>
        )}
      </main>
    );
  return <AtlasWorkspace graph={graph} />;
}
function AtlasWorkspace({ graph }: { graph: AtlasGraph }) {
  const [state, dispatch] = useReducer(
    (state: NavigationState, action: NavigationAction) =>
      navigate(graph, state, action),
    undefined,
    () => initialNavigation(!window.matchMedia('(max-width: 760px)').matches),
  );
  const [panel, setPanel] = useState<'source' | 'scope' | null>(null),
    [query, setQuery] = useState('');
  const [labelViewport, setLabelViewport] = useState<LabelViewport>();
  const sourceButton = useRef<HTMLButtonElement>(null),
    scopeButton = useRef<HTMLButtonElement>(null),
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
      data-dataset="aegra-real"
      data-selected={state.selected || ''}
      data-scope="network"
      data-flow-entry={state.flowEntry || ''}
      data-flow-paths={JSON.stringify(flow ? [...flow.paths] : [])}
      data-flow-terminals={JSON.stringify(flow ? [...flow.terminals] : [])}
      data-view={state.view}
      data-rail-open={state.railOpen}
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
      <header className="app-header">
        <a
          className="brand"
          href="#"
          onClick={(event) => event.preventDefault()}
          aria-label="CodeAtlas"
        >
          <Orbit size={23} strokeWidth={1.4} />
          <span>CodeAtlas</span>
        </a>
        <span className="header-divider" />
        <span className="repository-name">
          {scan.name}
          <small>{scan.tag}</small>
        </span>
        <span className="revision" title={graph.document.repo.revision}>
          {graph.document.repo.revision.slice(0, 7)}
        </span>
        <div className="header-right">
          <span className="live-dot" /> Code network
        </div>
      </header>
      <div className="canvas-area" ref={canvasArea}>
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
        />
        {state.railOpen && (
          <GraphControls
            graph={graph}
            state={state}
            dispatch={dispatch}
            returnFocus={railButton}
          />
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
          <span>AEGRA / CODE ATLAS</span>
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
        {panel && (
          <SourcePanel
            graph={graph}
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
                  onClick={() => dispatch({ type: 'toggle', id: selected.id })}
                >
                  {selected.kind === 'group'
                    ? state.collapsed.has(selected.id)
                      ? 'Open group'
                      : 'Collapse group'
                    : branchActionLabel(graph, state, selected.id)}
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
      <footer className="app-footer">
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
        </div>
        <button
          ref={scopeButton}
          className="scope-button"
          onClick={() => setPanel(panel === 'scope' ? null : 'scope')}
          aria-expanded={panel === 'scope'}
        >
          <span className="partial-dot" /> Partial static scan{' '}
          <span className="scope-extra">· 43 files · scope & coverage</span>
        </button>
      </footer>
    </main>
  );
}
