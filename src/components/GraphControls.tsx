import {
  Code2,
  Database,
  PanelLeftClose,
  Route as RouteIcon,
} from 'lucide-react';
import {
  useEffect,
  useRef,
  type Dispatch,
  type ReactNode,
  type RefObject,
} from 'react';
import {
  branchDepth,
  resolution,
  type NavigationAction,
  type NavigationState,
} from '../graph/navigation';
import { flowIndex } from '../graph/flow';
import type { AtlasGraph } from '../graph/types';
const views = [
  {
    id: 'code',
    label: 'Code',
    description: 'The complete recorded network',
    icon: Code2,
  },
  {
    id: 'entries',
    label: 'Entry points',
    description: 'HTTP routes into the code',
    icon: RouteIcon,
  },
  {
    id: 'data',
    label: 'Data flow',
    description: 'Recorded paths from entry points to data',
    icon: Database,
  },
] as const;
export type RailTab = 'findings' | 'endpoints' | 'files' | 'view';
/** The rail hosts the report's lists beside the graph; View keeps the graph controls. */
export function GraphControls({
  graph,
  state,
  dispatch,
  returnFocus,
  tabs,
  tab,
  onTab,
  children,
}: {
  graph: AtlasGraph;
  state: NavigationState;
  dispatch: Dispatch<NavigationAction>;
  returnFocus: RefObject<HTMLButtonElement | null>;
  tabs: { id: RailTab; label: string; count?: number; alert?: boolean }[];
  tab: RailTab;
  onTab: (tab: RailTab) => void;
  children?: ReactNode;
}) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const focusOnOpen = useRef(state.history.length > 0);
  useEffect(() => {
    const opener = returnFocus.current;
    if (focusOnOpen.current)
      closeButton.current?.focus({ preventScroll: true });
    return () => {
      if (opener?.isConnected) opener.focus({ preventScroll: true });
    };
  }, [returnFocus]);
  const detail = resolution(graph, state),
    depth = branchDepth(graph, state);
  const entries = graph.baseIds.filter(
    (id) => graph.nodes.get(id)!.groupedRoutes?.length,
  ).length;
  const accesses = flowIndex(graph).overview.terminals.size;
  const selected = state.selected ? graph.nodes.get(state.selected)! : null;
  return (
    <aside
      className={`graph-controls ${tab === 'view' ? '' : 'is-wide'}`}
      id="graph-controls"
      aria-label="Graph controls"
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          event.stopPropagation();
          dispatch({ type: 'rail', open: false });
        }
      }}
    >
      <div className="rail-header">
        <span>EXPLORE</span>
        <button
          className="icon-button"
          ref={closeButton}
          aria-label="Close graph controls"
          onClick={() => dispatch({ type: 'rail', open: false })}
        >
          <PanelLeftClose size={15} />
        </button>
      </div>
      <div className="rail-tabs" role="tablist" aria-label="Report sections">
        {tabs.map((item) => (
          <button
            key={item.id}
            role="tab"
            aria-selected={tab === item.id}
            aria-controls="rail-panel"
            onClick={() => onTab(item.id)}
          >
            {item.label}
            {item.count !== undefined && (
              <small className={item.alert ? 'is-alert' : ''}>
                {item.count}
              </small>
            )}
          </button>
        ))}
      </div>
      <div id="rail-panel" role="tabpanel">
        {tab !== 'view' ? (
          children
        ) : (
          <>
            <section className="rail-section">
              <h2>Graph view</h2>
              <div
                className="view-options"
                role="group"
                aria-label="Graph view"
              >
                {views.map(({ id, label, description, icon: Icon }) => (
                  <button
                    key={id}
                    aria-pressed={state.view === id}
                    onClick={() => dispatch({ type: 'view', view: id })}
                    title={description}
                  >
                    <Icon size={15} strokeWidth={1.6} />
                    <span>{label}</span>
                    <small>
                      {id === 'code'
                        ? graph.baseIds.length
                        : id === 'entries'
                          ? entries
                          : accesses}
                    </small>
                  </button>
                ))}
              </div>
              <p className="rail-note view-description">
                {state.view === 'code'
                  ? 'Indexed functions and classes, with their recorded connections.'
                  : state.view === 'entries'
                    ? `${entries} route handlers. Select one to trace every recorded path to data.`
                    : `${accesses} named access calls and their paths. Select an entry to include its other recorded data effects.`}
              </p>
            </section>
            <section className="rail-section">
              <div className="rail-section-heading">
                <h2>Resolution</h2>
                {detail === 'mixed' && <span>Mixed</span>}
              </div>
              <div
                className="segmented-control"
                role="group"
                aria-label="Graph resolution"
              >
                {(['files', 'functions'] as const).map((value) => (
                  <button
                    key={value}
                    aria-pressed={detail === value}
                    onClick={() =>
                      dispatch({ type: 'resolution', resolution: value })
                    }
                  >
                    {value === 'files' ? 'Files' : 'Symbols'}
                  </button>
                ))}
              </div>
              <div className="rail-section-heading depth-heading">
                <h3>Call depth</h3>
                {depth === 'mixed' && <span>Mixed</span>}
              </div>
              <div
                className="depth-options"
                role="group"
                aria-label="Selected branch call depth"
                aria-describedby="depth-description"
              >
                {([0, 1, 2, 3] as const).map((value) => (
                  <button
                    key={value}
                    disabled={depth === null}
                    aria-pressed={depth === value}
                    aria-label={`Call depth ${value}`}
                    onClick={() => dispatch({ type: 'depth', depth: value })}
                  >
                    {value}
                  </button>
                ))}
              </div>
              <p className="rail-note depth-description" id="depth-description">
                {depth === null ? (
                  'Select a handler or a call with recorded children.'
                ) : (
                  <>
                    <span title={selected!.name}>{selected!.name}</span> ·
                    selected branch only
                    {state.flowEntry
                      ? ' · changing depth clears entry flow'
                      : ''}
                    {state.view === 'data' ? ' · overview paths remain' : ''}
                  </>
                )}
              </p>
            </section>
            <section
              className="rail-section visual-key"
              aria-label="Graph visual key"
            >
              <h2>Reading the graph</h2>
              <div className="key-row">
                <i className="key-entry">↗</i>
                <span>Entry point</span>
                <i className="key-function" />
                <span>Code symbol</span>
              </div>
              <div className="key-effects">
                <span>
                  <i className="effect-badge read">R</i>Read
                </span>
                <span>
                  <i className="effect-badge write">W</i>Write
                </span>
                <span>
                  <i className="effect-badge both">RW</i>Both
                </span>
              </div>
              <p className="rail-note">
                Function badges summarize recorded object accesses in that body.
                A mint ↗ marks an entry point, including those with data access.
              </p>
              <div className="key-line">
                <i /> <span>Recorded call →</span>
              </div>
              <div className="key-line unresolved">
                <i /> <span>Unresolved target</span>
              </div>
              <p className="rail-note key-footnote">
                {state.view === 'code'
                  ? 'Clusters are source files.'
                  : 'Positions follow the view’s roles.'}
                <br />
                Arrows are calls, not execution order.
              </p>
            </section>
          </>
        )}
      </div>
    </aside>
  );
}
