import {
  Fragment,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from 'react';
import { ArrowLeft, ArrowRight, ChevronRight, Code2, ListFilter, Orbit } from 'lucide-react';
import { loadScan, scan } from './data';
import { routeGraph, visibleIds } from './graph/adapter';
import { overviewGraph, routeGroups } from './graph/catalog';
import { initialCamera, layoutGraph } from './graph/layout';
import { initialNavigation, navigate } from './graph/navigation';
import type { AtlasGraph } from './graph/types';
import { GraphCanvas } from './components/GraphCanvas';
import { SourcePanel } from './components/SourcePanel';
import { RouteDirectory } from './components/RouteDirectory';

export default function App() {
  const [graph, setGraph] = useState<AtlasGraph | null>(null);
  const [error, setError] = useState<string | null>(null);
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
        <h1>{error ? 'The scan could not be opened.' : 'Opening the Aegra scan…'}</h1>
        <p>{error || 'Loading recorded routes and source evidence.'}</p>
        {error && (
          <button className="secondary-button" onClick={() => window.location.reload()}>
            Try again
          </button>
        )}
      </main>
    );
  return <AtlasWorkspace graph={graph} />;
}

function AtlasWorkspace({ graph }: { graph: AtlasGraph }) {
  const [state, dispatch] = useReducer(
    (state: ReturnType<typeof initialNavigation>, action: Parameters<typeof navigate>[2]) =>
      navigate(graph, state, action),
    graph,
    (graph) => initialNavigation(graph, null),
  );
  const [panel, setPanel] = useState<'source' | 'scope' | null>(null);
  const [directory, setDirectory] = useState<{ file?: string } | null>(null);
  const sourceButton = useRef<HTMLButtonElement>(null);
  const scopeButton = useRef<HTMLButtonElement>(null);
  const routesButton = useRef<HTMLButtonElement>(null);
  const canvasArea = useRef<HTMLDivElement>(null);
  const overview = useMemo(() => overviewGraph(graph, scan.name), [graph]);
  const groups = useMemo(() => routeGroups(graph.document), [graph]);
  const scene = useMemo(
    () => (state.scope ? routeGraph(graph, state.scope) : overview),
    [graph, overview, state.scope],
  );
  const positions = useMemo(() => layoutGraph(scene), [scene]);
  const visible = useMemo(() => visibleIds(scene, state.path), [scene, state.path]);
  const selected = scene.nodes.get(state.selected)!;
  const isOpen = state.path.includes(selected.id);
  const partialRoutes = graph.document.routes.filter((route) =>
    Object.values(route.budget.coverage).some((coverage) => coverage !== 'complete'),
  ).length;
  const isOverview = state.scope === null;
  useLayoutEffect(() => {
    const element = canvasArea.current!;
    dispatch({
      type: 'camera',
      camera: initialCamera(layoutGraph(overview), overview, element.clientWidth, element.clientHeight),
    });
  }, [overview]);
  const closePanels = useCallback(() => {
    setPanel(null);
    setDirectory(null);
  }, []);
  function browse(file?: string) {
    setPanel(null);
    setDirectory({ file });
  }
  function chooseRoute(id: string) {
    closePanels();
    const next = routeGraph(graph, id);
    const element = canvasArea.current!;
    dispatch({
      type: 'focus-route',
      id,
      camera: initialCamera(layoutGraph(next), next, element.clientWidth, element.clientHeight),
    });
  }
  function toggle(id: string) {
    const node = scene.nodes.get(id)!;
    if (node.groupedRoutes) {
      browse(node.sourceFile);
      return;
    }
    closePanels();
    dispatch({ type: state.path.includes(id) ? 'collapse' : 'expand', id });
  }
  function back() {
    closePanels();
    dispatch({ type: 'back' });
  }
  function showOverview() {
    closePanels();
    dispatch({ type: 'overview' });
  }
  const actionLabel = selected.groupedRoutes
    ? `Browse ${selected.groupedRoutes.length} routes`
    : selected.children.length
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
      data-dataset="aegra-real"
      data-selected={state.selected}
      data-scope={state.scope || 'overview'}
      data-path={state.path.join('/')}
      onKeyDown={(event) => {
        if (event.key === 'Escape' && !event.defaultPrevented) {
          if (panel || directory) closePanels();
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
            showOverview();
          }}
          aria-label="CodeAtlas, all routes"
        >
          <Orbit size={23} strokeWidth={1.4} />
          <span>CodeAtlas</span>
        </a>
        <span className="active-tab">Code graph</span>
        <span className="repository-name">
          {scan.name} <small>{scan.tag}</small>
        </span>
        <span className="revision" title={graph.document.repo.revision}>
          {graph.document.repo.revision.slice(0, 7)}
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
          <button onClick={showOverview} aria-current={isOverview ? 'page' : undefined}>
            All routes
          </button>
          {!isOverview && (
            <>
              <ChevronRight size={12} />
              <button
                onClick={() => {
                  closePanels();
                  dispatch({ type: 'breadcrumb', depth: 0 });
                }}
                aria-current={!state.path.length ? 'page' : undefined}
              >
                {scene.nodes.get(state.scope!)!.name}
              </button>
            </>
          )}
          {state.path.map((id, index) =>
            id === state.scope ? null : (
              <Fragment key={id}>
                <ChevronRight size={12} aria-hidden="true" />
                <button
                  title={scene.nodes.get(id)!.name}
                  aria-current={index === state.path.length - 1 ? 'page' : undefined}
                  onClick={() => {
                    closePanels();
                    dispatch({ type: 'breadcrumb', depth: index + 1 });
                  }}
                >
                  {scene.nodes.get(id)!.name}
                </button>
              </Fragment>
            ),
          )}
        </nav>
        <button
          ref={routesButton}
          className="route-directory-button"
          onClick={() => (directory ? setDirectory(null) : browse())}
          aria-expanded={!!directory}
        >
          <ListFilter size={15} />
          Routes <span>{graph.document.routes.length}</span>
        </button>
      </div>
      <div className="scope-line">
        <span className="scope-status">
          <i />
          Real scan <span>·</span> {graph.document.routes.length} routes <span>·</span>{' '}
          {graph.document.symbolIndex.length} symbols
        </span>
        <span className="scope-context">
          {isOverview
            ? `${groups.length} source files · ${partialRoutes} routes with partial coverage`
            : `Focused route · ${scene.nodes.get(state.scope!)!.subtitle}`}
        </span>
      </div>
      <div className="canvas-area" ref={canvasArea}>
        <GraphCanvas
          key={state.scope || 'overview'}
          graph={scene}
          positions={positions}
          visible={visible}
          state={state}
          dispatch={dispatch}
          onToggle={toggle}
        />
        {directory && (
          <RouteDirectory
            key={directory.file || 'all'}
            groups={groups}
            file={directory.file}
            selected={state.scope}
            onChoose={chooseRoute}
            onClose={() => setDirectory(null)}
            returnFocus={routesButton}
          />
        )}
        {panel && (
          <SourcePanel
            graph={graph}
            node={selected}
            mode={panel}
            onClose={() => setPanel(null)}
            returnFocus={panel === 'source' ? sourceButton : scopeButton}
          />
        )}
        {isOverview && !directory && !panel && (
          <div className="overview-caption">
            <span>REPOSITORY / SOURCE FILES</span>
            <p>Choose a file, then follow a route.</p>
          </div>
        )}
      </div>
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
                      : selected.kind === 'group'
                        ? 'source file'
                        : selected.kind === 'repository'
                          ? 'scan overview'
                          : 'call occurrence'}
            </span>
          </div>
          <small>
            {selected.sourceFile ||
              (selected.kind === 'repository'
                ? `${groups.length} source files · includes example code · no agent review`
                : selected.kind === 'route'
                  ? selected.subtitle
                  : selected.range
                    ? `${selected.range.file}:${selected.range.startLine}–${selected.range.endLine}`
                    : selected.subtitle)}
          </small>
        </div>
        <div className="selection-actions">
          {!isOverview && (
            <button
              ref={sourceButton}
              className="secondary-button"
              onClick={() => {
                setDirectory(null);
                setPanel(panel === 'source' ? null : 'source');
              }}
              aria-expanded={panel === 'source'}
              aria-controls={panel === 'source' ? 'source-panel' : undefined}
            >
              <Code2 size={15} />
              Source
            </button>
          )}
          <button
            className="primary-button"
            onClick={() => toggle(selected.id)}
            disabled={!selected.children.length && !selected.groupedRoutes}
          >
            {actionLabel}
            {(selected.groupedRoutes || (selected.children.length > 0 && !isOpen)) && (
              <ArrowRight size={15} />
            )}
          </button>
        </div>
      </section>
      <footer className="app-footer">
        <div className="legend" aria-label="Graph relationship legend">
          {isOverview ? (
            <span>
              <i className="legend-line contains" />
              Source grouping · not calls
            </span>
          ) : (
            <>
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
            </>
          )}
        </div>
        <button
          ref={scopeButton}
          className="scope-button"
          onClick={() => {
            setDirectory(null);
            setPanel(panel === 'scope' ? null : 'scope');
          }}
          aria-expanded={panel === 'scope'}
          title="Real scan provenance and coverage"
        >
          Real scan · scope & coverage
        </button>
        <span className="node-count">{visible.size} nodes</span>
      </footer>
      <div className="sr-only" role="status" aria-live="polite">
        {isOverview
          ? `All ${graph.document.routes.length} routes grouped by source file`
          : `Focused route ${scene.nodes.get(state.scope!)!.name}`}
        . {visible.size} visible nodes. Selected {selected.name}.
      </div>
    </main>
  );
}
