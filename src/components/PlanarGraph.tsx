import { useLayoutEffect, useMemo, useReducer, useRef, useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  Code2,
  Database,
  Flag,
  PanelLeft,
  Search,
  X,
} from 'lucide-react';
import type { FileManifest } from '../api';
import { sourceIdentity, type ScanSource } from '../source';
import {
  nodeFindingKind,
  type FindingIndex,
  type FindingItem,
} from '../graph/findings';
import { ViewAnchors } from '../graph/view-layout';
import { matchingSymbols } from '../graph/catalog';
import type { LabelViewport } from '../graph/labels';
import { initialCamera, layoutGraph } from '../graph/layout';
import {
  primaryNodeAction,
  navigationVisibleIds,
  activeFlow,
  initialNavigation,
  navigate,
  type NavigationAction,
  type NavigationState,
} from '../graph/navigation';
import type { AtlasGraph, Route } from '../graph/types';
import { GraphCanvas } from './GraphCanvas';
import { SourcePanel } from './SourcePanel';
import { GraphControls, type RailTab } from './GraphControls';
import { FindingPanel } from './FindingsPanel';
import { EndpointsList, FileTree } from './Navigator';
import { projectTree } from '../graph/project';
import {
  accessSummary,
  dataEffect,
  effectGlyph,
  effectLabel,
} from '../graph/semantics';

import type { ProjectView, TraceTarget } from '../ProjectReport';

export function PlanarGraph({
  graph,
  source,
  manifest,
  findings,
  trace,
  onViewChange,
}: {
  graph: AtlasGraph;
  source: ScanSource;
  manifest: FileManifest | null;
  findings: FindingIndex | null;
  trace: TraceTarget | null;
  onViewChange: (view: ProjectView) => void;
}) {
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
  const [railTab, setRailTab] = useState<RailTab>('view');
  const identity = sourceIdentity(source);
  const focused = findings?.items.find((item) => item.id === focusedId) || null;
  // The path stays emphasized while its entry flow is active; Back restores it.
  const findingPath = useMemo(
    () =>
      focused &&
      state.flowEntry === focused.handlerId &&
      (!state.flowRoute || state.flowRoute === focused.route.id)
        ? new Set(focused.path)
        : null,
    [focused, state.flowEntry, state.flowRoute],
  );
  const findingMarks = useMemo(() => {
    const marks = new Map<string, 'finding' | 'candidate'>();
    for (const [id, items] of findings?.byNode || []) {
      const applicable =
        state.flowRoute && id === state.flowEntry
          ? items.filter((item) => item.route.id === state.flowRoute)
          : items;
      const kind = nodeFindingKind(applicable);
      if (kind) marks.set(id, kind);
    }
    return marks;
  }, [findings, state.flowEntry, state.flowRoute]);
  const [labelViewport, setLabelViewport] = useState<LabelViewport>();
  const sourceButton = useRef<HTMLButtonElement>(null),
    scopeButton = useRef<HTMLButtonElement>(null),
    findingOpener = useRef<HTMLElement | null>(null),
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
      state.flowRoute,
      state.view,
    ],
  );
  const positions = useMemo(
    () => anchors.ensure(state.view, visible),
    [anchors, state.view, visible],
  );
  const matches = useMemo(() => matchingSymbols(graph, query), [graph, query]);
  const flow = activeFlow(graph, state);
  const flowHandler = state.flowEntry
    ? graph.nodes.get(state.flowEntry)!
    : null;
  const route = flowHandler?.groupedRoutes?.find(
    (route) => route.id === state.flowRoute,
  );
  const selectedNode = state.selected ? graph.nodes.get(state.selected)! : null;
  const selected =
    selectedNode && route && selectedNode.id === route.handler.symbolId
      ? {
          ...selectedNode,
          route,
          groupedRoutes: [route],
          accesses: selectedNode.accesses.filter(
            (record) => record.route.id === route.id,
          ),
          authSteps: selectedNode.authSteps.filter(
            (record) => record.route.id === route.id,
          ),
        }
      : selectedNode;
  const selectedAction = selected
    ? primaryNodeAction(graph, state, selected.id)
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
  const cameraInitialized = useRef(false);
  const handledTrace = useRef<TraceTarget | null>(null);
  useLayoutEffect(() => {
    const element = canvasArea.current!;
    const { clientWidth: width, clientHeight: height } = element;
    if (trace && trace !== handledTrace.current) {
      handledTrace.current = trace;
      const position = layout.positions.get(trace.handlerId);
      const scale = Math.max(0.8, state.camera.scale);
      dispatch({
        type: 'reveal',
        id: trace.handlerId,
        routeId: trace.routeId,
        camera: position
          ? {
              scale,
              x: width / 2 - position.x * scale,
              y: height / 2 - position.y * scale,
            }
          : undefined,
      });
      setFocusedId(trace.findingId || null);
      setPanel(trace.findingId ? 'finding' : null);
      element
        .querySelector<HTMLElement>('.graph-viewport')
        ?.focus({ preventScroll: true });
    } else if (!cameraInitialized.current) {
      dispatch({
        type: 'camera',
        camera: initialCamera(layout, graph, width, height),
      });
    }
    cameraInitialized.current = true;
  }, [layout, graph, trace, state.camera.scale]);
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
    if (item && state.flowRoute !== item.route.id)
      dispatch({
        type: 'reveal',
        id: item.handlerId,
        routeId: item.route.id,
        camera: centered(item.handlerId),
      });
  }
  function stepTo(item: FindingItem, id: string) {
    if (state.flowRoute !== item.route.id || id === item.handlerId)
      dispatch({ type: 'reveal', id: item.handlerId, routeId: item.route.id });
    if (id !== item.handlerId) dispatch({ type: 'select', id });
  }
  function openFinding(item: FindingItem) {
    findingOpener.current = document.activeElement as HTMLElement | null;
    setPanel('finding');
    focusFinding(item);
  }
  function openEndpoint(route: Route) {
    if (state.view === 'code' && state.flowRoute === route.id) return;
    const id = route.handler.symbolId;
    dispatch({ type: 'reveal', id, routeId: route.id, camera: centered(id) });
    setPanel(null);
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
  const selectedFindings = selected
    ? findings?.byNode
        .get(selected.id)
        ?.filter((item) => !route || item.route.id === route.id)
    : null;
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
    <section
      className="atlas-app report-planar"
      aria-label="2D graph"
      data-renderer="2d"
      data-dataset={source.kind === 'sample' ? 'aegra-real' : 'scan'}
      data-finding-focus={findingPath ? focused!.id : ''}
      data-selected={state.selected || ''}
      data-scope="network"
      data-flow-entry={state.flowEntry || ''}
      data-flow-route={state.flowRoute || ''}
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
      <div className="report-planar-body">
        {state.railOpen && (
          <GraphControls
            graph={graph}
            state={state}
            dispatch={dispatch}
            returnFocus={railButton}
            tab={railTab}
            onTab={setRailTab}
            tabs={[
              { id: 'view', label: 'View' },
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
            ]}
          >
            {railTab === 'files' ? (
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
                activeRoute={state.flowRoute}
                onOpen={openEndpoint}
              />
            )}
          </GraphControls>
        )}
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
            findingMarks={findingMarks}
            findingPath={findingPath}
          />
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
                  <button
                    onClick={() => setQuery('')}
                    aria-label="Clear search"
                  >
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
              <strong>
                {route
                  ? `${route.httpMethod} ${route.pathTemplate}`
                  : flowHandler!.name}
              </strong>
              <p>
                {flow.terminals.size
                  ? `${flow.terminals.size} recorded data operations · ${[...flow.terminals].filter((id) => graph.nodes.get(id)!.accesses.length).length} with named objects`
                  : 'No data path recorded for this entry.'}
              </p>
              <small>
                Static route slice ·{' '}
                {flow.paths.size &&
                [...flow.paths].some(
                  (id) => graph.nodes.get(id)!.kind === 'auth',
                )
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
              returnFocus={findingOpener}
            />
          )}
          {(panel === 'source' || panel === 'scope') && (
            <SourcePanel
              graph={graph}
              source={source}
              node={selected || graph.nodes.get(graph.defaultId)!}
              mode={panel}
              routeId={selectedNode === flowHandler ? route?.id : undefined}
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
                {!!selectedFindings?.length && (
                  <button
                    className={`secondary-button related-findings ${nodeFindingKind(selectedFindings)}`}
                    onClick={() =>
                      selectedFindings.length === 1
                        ? openFinding(selectedFindings[0])
                        : onViewChange('issues')
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
                    onClick={() =>
                      setPanel(panel === 'source' ? null : 'source')
                    }
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
          <span className="partial-dot" /> Scan coverage{' '}
          <span className="scope-extra">· {graph.groups.length} files</span>
        </button>
      </footer>
    </section>
  );
}
