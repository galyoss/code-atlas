import { Fragment, useCallback, useMemo, useReducer, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, ChevronDown, ChevronRight, Code2, Orbit } from 'lucide-react';
import { datasets, type DatasetId } from './data';
import { visibleIds } from './graph/adapter';
import { layoutGraph } from './graph/layout';
import { initialNavigation, navigate, type NavigationAction } from './graph/navigation';
import { GraphCanvas } from './components/GraphCanvas';
import { SourcePanel } from './components/SourcePanel';

export default function App() {
  const [dataset, setDataset] = useState<DatasetId>('aegra');
  return <AtlasWorkspace key={dataset} dataset={dataset} setDataset={setDataset} />;
}
function AtlasWorkspace({
  dataset,
  setDataset,
}: {
  dataset: DatasetId;
  setDataset: (id: DatasetId) => void;
}) {
  const graph = datasets[dataset];
  const [state, rawDispatch] = useReducer(
    (state: ReturnType<typeof initialNavigation>, action: NavigationAction) => navigate(graph, state, action),
    graph,
    initialNavigation,
  );
  const [panel, setPanel] = useState<'source' | 'scope' | null>(null);
  const sourceButton = useRef<HTMLButtonElement>(null);
  const scopeButton = useRef<HTMLButtonElement>(null);
  const dispatch = useCallback((action: NavigationAction) => {
    rawDispatch(action);
  }, []);
  const positions = useMemo(() => layoutGraph(graph), [graph]);
  const visible = useMemo(() => visibleIds(graph, state.path), [graph, state.path]);
  const selected = graph.nodes.get(state.selected)!;
  const isOpen = state.path.includes(selected.id);
  const partial = graph.document.routes.some((route) =>
    Object.values(route.budget.coverage).some((coverage) => coverage !== 'complete'),
  );
  function toggle(id: string) {
    setPanel(null);
    dispatch({ type: state.path.includes(id) ? 'collapse' : 'expand', id });
  }
  function back() {
    setPanel(null);
    dispatch({ type: 'back' });
  }
  const actionLabel = selected.children.length
    ? isOpen
      ? 'Collapse calls'
      : `Open ${selected.children.length} calls`
    : selected.kind === 'gap'
      ? 'Unresolved target'
      : selected.kind === 'auth'
        ? 'Auth context'
        : selected.kind === 'model'
          ? 'Data summary'
          : selected.call?.expanded === 'no'
            ? 'No recorded children'
            : 'No further calls';
  return (
    <main
      className="atlas-app"
      data-dataset={dataset}
      data-selected={state.selected}
      data-path={state.path.join('/')}
      onKeyDown={(event) => {
        if (event.key === 'Escape' && !event.defaultPrevented) {
          if (panel) setPanel(null);
          else back();
        }
      }}
    >
      <header className="app-header">
        <a
          className="brand"
          href="#"
          onClick={(event) => {
            event.preventDefault();
            setPanel(null);
            dispatch({ type: 'breadcrumb', depth: 0 });
          }}
          aria-label="CodeAtlas, all routes"
        >
          <Orbit size={23} strokeWidth={1.4} />
          <span>CodeAtlas</span>
        </a>
        <span className="active-tab">Code graph</span>
        <div className="repository-select">
          <label className="sr-only" htmlFor="repository">
            Repository example
          </label>
          <select
            id="repository"
            value={dataset}
            onChange={(event) => setDataset(event.target.value as DatasetId)}
          >
            {Object.entries(datasets).map(([id, item]) => (
              <option key={id} value={id}>
                {item.document.repo.name}
              </option>
            ))}
          </select>
          <ChevronDown size={13} aria-hidden="true" />
        </div>
        <span className="revision" title={graph.document.repo.revision}>
          {graph.document.repo.revision === 'illustrative'
            ? 'illustrative'
            : graph.document.repo.revision.slice(0, 7)}
        </span>
        <span className="header-label">ATLAS</span>
      </header>
      <div className="exploration-toolbar">
        <button
          className="icon-button back-button"
          onClick={back}
          disabled={!state.history.length}
          aria-label="Back to previous view"
          title="Back to previous view"
        >
          <ArrowLeft size={17} />
        </button>
        <nav className="breadcrumbs" aria-label="Graph exploration path">
          <button
            onClick={() => {
              setPanel(null);
              dispatch({ type: 'breadcrumb', depth: 0 });
            }}
            aria-current={!state.path.length ? 'page' : undefined}
          >
            All routes
          </button>
          {state.path.map((id, index) => (
            <Fragment key={id}>
              <ChevronRight size={12} aria-hidden="true" />
              <button
                title={graph.nodes.get(id)!.name}
                aria-current={index === state.path.length - 1 ? 'page' : undefined}
                onClick={() => {
                  setPanel(null);
                  dispatch({ type: 'breadcrumb', depth: index + 1 });
                }}
              >
                {graph.nodes.get(id)!.name}
              </button>
            </Fragment>
          ))}
        </nav>
        <span className="detail-level">{state.path.length ? `Depth ${state.path.length}` : 'Overview'}</span>
      </div>
      <div className="scope-line">
        <span className="scope-status">
          <i />
          {graph.document.routes.length} route slices <span>·</span>{' '}
          {partial ? 'partial coverage' : 'complete within slices'}
        </span>
        <span className="scope-context">
          Handler calls <span>·</span> auth context collapsed
        </span>
      </div>
      <GraphCanvas
        graph={graph}
        positions={positions}
        visible={visible}
        state={state}
        dispatch={dispatch}
        onToggle={toggle}
      >
        {panel && (
          <SourcePanel
            graph={graph}
            node={selected}
            mode={panel}
            onClose={() => setPanel(null)}
            returnFocus={panel === 'source' ? sourceButton : scopeButton}
          />
        )}
      </GraphCanvas>
      <section className="selection-bar" aria-label="Selected node">
        <div className="selection-copy">
          <div className="selection-heading">
            <span className={`selection-dot ${selected.kind}`} />
            <strong>{selected.name}</strong>
            <span className="selection-kind">
              {selected.kind === 'route'
                ? 'route handler'
                : selected.kind === 'gap'
                  ? 'unresolved call'
                  : selected.kind === 'model'
                    ? 'data summary'
                    : selected.kind === 'auth'
                      ? 'auth context'
                      : 'call occurrence'}
            </span>
          </div>
          <small>
            {selected.kind === 'route'
              ? selected.subtitle
              : selected.range
                ? `${selected.range.file}:${selected.range.startLine}–${selected.range.endLine}`
                : selected.subtitle}
          </small>
        </div>
        <div className="selection-actions">
          <button
            ref={sourceButton}
            className="secondary-button"
            onClick={() => setPanel(panel === 'source' ? null : 'source')}
            aria-expanded={panel === 'source'}
            aria-controls={panel === 'source' ? 'source-panel' : undefined}
          >
            <Code2 size={15} />
            Source
          </button>
          <button
            className="primary-button"
            onClick={() => toggle(selected.id)}
            disabled={!selected.children.length}
          >
            {actionLabel}
            {selected.children.length > 0 && !isOpen && <ArrowRight size={15} />}
          </button>
        </div>
      </section>
      <footer className="app-footer">
        <div className="legend" aria-label="Graph relationship legend">
          <span>
            <i className="legend-line call" />
            Calls
          </span>
          <span>
            <i className="legend-line summary" />
            Data summary
          </span>
          <span>
            <i className="legend-line context" />
            Auth / unresolved
          </span>
        </div>
        <button
          ref={scopeButton}
          className="scope-button"
          onClick={() => setPanel(panel === 'scope' ? null : 'scope')}
          aria-expanded={panel === 'scope'}
          title="About this example and its coverage"
        >
          Hand-authored example
        </button>
        <span className="node-count">{visible.size} nodes</span>
      </footer>
      <div className="sr-only" role="status" aria-live="polite">
        {state.path.length ? state.path.map((id) => graph.nodes.get(id)!.name).join(', ') : 'All routes'}.{' '}
        {visible.size} visible nodes. Selected {selected.name}.
      </div>
    </main>
  );
}
