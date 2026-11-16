import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from 'react';
import { ArrowLeft, ArrowRight, Code2, Orbit, Search, X } from 'lucide-react';
import { loadScan, scan } from './data';
import { visibleIds } from './graph/adapter';
import { matchingSymbols } from './graph/catalog';
import { DetailAnchors, initialCamera, layoutGraph } from './graph/layout';
import {
  initialNavigation,
  navigate,
  type NavigationAction,
  type NavigationState,
} from './graph/navigation';
import type { AtlasGraph } from './graph/types';
import { GraphCanvas } from './components/GraphCanvas';
import { SourcePanel } from './components/SourcePanel';

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
    initialNavigation,
  );
  const [panel, setPanel] = useState<'source' | 'scope' | null>(null),
    [query, setQuery] = useState('');
  const sourceButton = useRef<HTMLButtonElement>(null),
    scopeButton = useRef<HTMLButtonElement>(null),
    canvasArea = useRef<HTMLDivElement>(null);
  const layout = useMemo(() => layoutGraph(graph), [graph]);
  const anchors = useMemo(() => new DetailAnchors(layout), [layout]);
  const visible = useMemo(
    () => visibleIds(graph, state.expanded, state.collapsed),
    [graph, state.expanded, state.collapsed],
  );
  const positions = useMemo(
    () => anchors.ensure(graph, visible),
    [anchors, graph, visible],
  );
  const matches = useMemo(() => matchingSymbols(graph, query), [graph, query]);
  const selected = state.selected ? graph.nodes.get(state.selected)! : null;
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
      data-expanded={JSON.stringify([...state.expanded])}
      data-collapsed={JSON.stringify([...state.collapsed])}
      onKeyDown={(event) => {
        if (event.key === 'Escape' && !event.defaultPrevented) {
          if (panel) setPanel(null);
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
          positions={positions}
          visible={visible}
          state={state}
          dispatch={dispatch}
          matches={matches}
          searching={!!query.trim()}
        />
        <div className="network-toolbar">
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
            {symbolsVisible} symbols <i>·</i>{' '}
            {graph.edges.filter((edge) => edge.aggregated).length} recorded call
            links
            {detailCount > 0 && (
              <>
                {' '}
                <i>·</i> {detailCount} detail nodes
              </>
            )}
          </p>
        </div>
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
            </div>
            <div className="selection-actions">
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
                    : state.expanded.has(selected.id)
                      ? 'Collapse calls'
                      : 'Open detail'}
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
            <i className="legend-dot handler" /> Handler
          </span>
          <span>
            <i className="legend-dot symbol" /> Symbol
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
