import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type Dispatch,
  type KeyboardEvent,
  type PointerEvent,
} from 'react';
import { LocateFixed, Maximize, Minus, Plus } from 'lucide-react';
import { flowIndex } from '../graph/flow';
import type { RoleCaption } from '../graph/view-layout';
import { accessPathIds, visibleEdges } from '../graph/adapter';
import {
  dataEffect,
  effectGlyph,
  emphasized,
  semanticDescription,
  nodeLabel,
} from '../graph/semantics';
import { placeLabels, type LabelViewport } from '../graph/labels';
import { fitCamera, zoomCamera, type NetworkLayout } from '../graph/layout';
import type { AtlasGraph, Point } from '../graph/types';
import {
  activeFlow,
  branchOpen,
  type NavigationAction,
  type NavigationState,
} from '../graph/navigation';
import { useAnimatedScene } from '../hooks/useAnimatedScene';
interface Props {
  graph: AtlasGraph;
  layout: NetworkLayout;
  captions: RoleCaption[];
  positions: Map<string, Point>;
  visible: Set<string>;
  state: NavigationState;
  dispatch: Dispatch<NavigationAction>;
  matches: string[];
  searching: boolean;
  labelViewport?: LabelViewport;
  /** Handlers and cited access occurrences that carry a finding or candidate. */
  findingMarks?: Map<string, 'finding' | 'candidate'>;
  /** The focused finding's recorded path from its handler to the cited access. */
  findingPath?: Set<string> | null;
}

export function GraphCanvas({
  graph,
  layout,
  captions,
  positions,
  visible,
  state,
  dispatch,
  matches,
  searching,
  labelViewport,
  findingMarks,
  findingPath,
}: Props) {
  const viewport = useRef<HTMLDivElement>(null);
  const drag = useRef<{ id: number; origin: Point; camera: Point } | null>(
    null,
  );
  const camera = useRef(state.camera);
  camera.current = state.camera;
  const [hovered, setHovered] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const { poses, transitioning } = useAnimatedScene(graph, positions, visible);
  // Retain disappearing edges until their endpoints have reached the parent anchor.
  const poseIds = new Set(poses.keys());
  const edges = visibleEdges(graph, poseIds, state.collapsed);
  const active = hovered || state.selected;
  const flow = activeFlow(graph, state);
  const focusPaths = useMemo(
    () =>
      flow
        ? new Set([...flow.paths, ...flow.definitions])
        : state.accessFocus && state.selected === state.accessFocus
          ? accessPathIds(graph, state.accessFocus)
          : new Set<string>(),
    [graph, flow, state.accessFocus, state.selected],
  );
  const neighbors = new Set<string>(
    focusPaths.size
      ? [...focusPaths, ...(state.selected ? [state.selected] : [])]
      : active
        ? [active]
        : [],
  );
  for (const edge of edges)
    if (!focusPaths.size && (edge.from === active || edge.to === active)) {
      neighbors.add(edge.from);
      neighbors.add(edge.to);
    }
  const matchSet = new Set(matches);
  const landmarks = useMemo(() => {
    const degree = new Map<string, number>();
    for (const edge of graph.edges.filter((edge) => edge.aggregated))
      for (const id of [edge.from, edge.to])
        degree.set(id, (degree.get(id) || 0) + 1);
    return [...graph.baseIds].sort(
      (a, b) => (degree.get(b) || 0) - (degree.get(a) || 0),
    );
  }, [graph]);
  const priority = [
    ...(findingPath || []),
    ...[...focusPaths].filter(
      (id) =>
        graph.nodes.get(id)!.accesses.length && !graph.nodes.get(id)!.canonical,
    ),
    // Recorded children and actual neighbors get first claim on available label space.
    ...(active ? graph.nodes.get(active)!.children : []),
    ...neighbors,
    ...matches,
    ...(state.view === 'data' ? [...flowIndex(graph).overview.terminals] : []),
    ...(state.view === 'code'
      ? []
      : graph.baseIds.filter((id) =>
          emphasized(graph.nodes.get(id)!, state.view),
        )),
    ...landmarks,
  ];
  const renderedVisible =
    state.view === 'code'
      ? visible
      : new Set(
          [...visible].filter(
            (id) =>
              graph.nodes.get(id)!.kind !== 'group' || state.collapsed.has(id),
          ),
        );
  const labels = placeLabels(
    graph,
    positions,
    renderedVisible,
    priority,
    state.camera.scale,
    active,
    labelViewport ? { ...labelViewport, camera: state.camera } : undefined,
  );
  const size = () => ({
    width: viewport.current!.clientWidth,
    height: viewport.current!.clientHeight,
  });
  const zoom = (factor: number) => {
    const { width, height } = size();
    dispatch({
      type: 'camera',
      camera: zoomCamera(camera.current, factor, {
        x: width / 2,
        y: height / 2,
      }),
    });
  };
  useEffect(() => {
    const element = viewport.current!;
    const wheel = (event: WheelEvent) => {
      if ((event.target as Element).closest('aside')) return;
      event.preventDefault();
      const rect = element.getBoundingClientRect();
      dispatch({
        type: 'camera',
        camera: zoomCamera(camera.current, Math.exp(-event.deltaY * 0.0015), {
          x: event.clientX - rect.left,
          y: event.clientY - rect.top,
        }),
      });
    };
    element.addEventListener('wheel', wheel, { passive: false });
    return () => element.removeEventListener('wheel', wheel);
  }, [dispatch]);
  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (
      event.button !== 0 ||
      (event.target as Element).closest('button, aside, a, input')
    )
      return;
    event.currentTarget.focus({ preventScroll: true });
    drag.current = {
      id: event.pointerId,
      origin: { x: event.clientX, y: event.clientY },
      camera: state.camera,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragging(true);
  };
  const stopDrag = () => {
    drag.current = null;
    setDragging(false);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.target !== event.currentTarget) return;
    const delta = (
      {
        ArrowLeft: [60, 0],
        ArrowRight: [-60, 0],
        ArrowUp: [0, 60],
        ArrowDown: [0, -60],
      } as Record<string, number[]>
    )[event.key];
    if (delta) {
      event.preventDefault();
      dispatch({
        type: 'camera',
        camera: {
          ...state.camera,
          x: state.camera.x + delta[0],
          y: state.camera.y + delta[1],
        },
      });
    } else if (event.key === '+' || event.key === '=') {
      event.preventDefault();
      zoom(1.15);
    } else if (event.key === '-') {
      event.preventDefault();
      zoom(1 / 1.15);
    }
  };
  return (
    <div
      ref={viewport}
      className={`graph-viewport ${dragging ? 'is-dragging' : ''}`}
      tabIndex={0}
      role="region"
      aria-label="Code network. Drag or use arrow keys to pan. Wheel, plus and minus zoom. Select an entry to trace its recorded data flow."
      data-transitioning={transitioning}
      data-camera={JSON.stringify(state.camera)}
      onKeyDown={onKeyDown}
      onPointerDown={onPointerDown}
      onPointerMove={(event) => {
        if (!drag.current || drag.current.id !== event.pointerId) return;
        dispatch({
          type: 'camera',
          camera: {
            ...state.camera,
            x: drag.current.camera.x + event.clientX - drag.current.origin.x,
            y: drag.current.camera.y + event.clientY - drag.current.origin.y,
          },
        });
      }}
      onPointerUp={stopDrag}
      onPointerCancel={stopDrag}
      onLostPointerCapture={stopDrag}
    >
      <div
        className="graph-surface"
        style={
          {
            transform: `translate(${state.camera.x}px, ${state.camera.y}px) scale(${state.camera.scale})`,
            '--inverse-scale': 1 / state.camera.scale,
          } as CSSProperties
        }
      >
        <svg className="graph-lines" width="1" height="1" aria-hidden="true">
          <defs>
            <marker
              id="call-arrow"
              viewBox="0 0 8 8"
              refX="7"
              refY="4"
              markerWidth="4"
              markerHeight="4"
              orient="auto-start-reverse"
            >
              <path d="M0 0L8 4L0 8Z" fill="context-stroke" />
            </marker>
          </defs>
          {graph.groups.map((group) => {
            const region = layout.regions.get(group.id)!;
            return (
              <circle
                key={group.id}
                className={`group-region ${state.collapsed.has(group.id) || state.view !== 'code' ? 'is-collapsed' : ''}`}
                cx={region.x}
                cy={region.y}
                r={region.radius}
              />
            );
          })}
          {edges.map((edge) => {
            const a = poses.get(edge.from)!,
              b = poses.get(edge.to)!;
            const onFindingPath =
              !!findingPath &&
              !edge.aggregated &&
              findingPath.has(edge.from) &&
              findingPath.has(edge.to);
            const linked = flow
              ? flow.edges.has(edge.id)
              : focusPaths.size
                ? (edge.kind === 'call' || edge.kind === 'unresolved') &&
                  focusPaths.has(edge.from) &&
                  focusPaths.has(edge.to)
                : edge.from === active || edge.to === active;
            const angle = Math.atan2(b.y - a.y, b.x - a.x),
              padding = 10;
            const end = {
              x: b.x - Math.cos(angle) * padding,
              y: b.y - Math.sin(angle) * padding,
            };
            const path =
              edge.from === edge.to
                ? `M${a.x} ${a.y - 8} C${a.x + 34} ${a.y - 43} ${a.x + 40} ${a.y + 22} ${a.x + 8} ${a.y}`
                : `M${a.x} ${a.y} L${end.x} ${end.y}`;
            return (
              <path
                key={edge.id}
                data-edge-id={edge.id}
                data-from={edge.from}
                data-to={edge.to}
                data-kind={edge.kind}
                data-flow-edge={!!flow?.edges.has(edge.id)}
                data-evidence-count={edge.evidence.length}
                data-aggregated={!!edge.aggregated}
                data-finding-path={onFindingPath}
                className={`graph-edge ${edge.kind} ${linked ? 'is-highlighted' : ''} ${onFindingPath ? 'is-finding-path' : ''} ${(flow || active) && !linked ? 'is-muted' : ''}`}
                d={path}
                opacity={edge.aggregated ? 1 : Math.min(a.opacity, b.opacity)}
                markerEnd={
                  edge.kind === 'call' || edge.kind === 'unresolved'
                    ? 'url(#call-arrow)'
                    : undefined
                }
              />
            );
          })}
        </svg>
        {[...poses].map(([id, pose]) => {
          const node = graph.nodes.get(id)!,
            selected = state.selected === id,
            present = visible.has(id);
          if (node.kind === 'group') {
            if (state.view !== 'code' && !state.collapsed.has(id)) return null;
            const group = graph.groups.find((group) => group.id === id)!;
            const collapsed = state.collapsed.has(id);
            return (
              <button
                key={id}
                className={`file-toggle ${group.members.length >= 4 || collapsed ? 'has-label' : ''} ${selected ? 'is-selected' : ''}`}
                data-group-id={id}
                style={{ left: pose.x, top: pose.y }}
                title={`${group.file} · ${group.members.length} symbols`}
                aria-label={`${collapsed ? 'Expand' : 'Collapse'} file ${group.file}, ${group.members.length} symbols`}
                aria-expanded={!collapsed}
                onClick={() => dispatch({ type: 'toggle', id })}
              >
                <span className="file-toggle-icon">
                  {collapsed ? '+' : '−'}
                </span>
                <span className="file-name">{group.name}</span>
                <small>{group.members.length}</small>
              </button>
            );
          }
          const effect = dataEffect(node),
            highlighted = emphasized(node, state.view);
          const dimmed = flow
            ? !focusPaths.has(id)
            : active
              ? !neighbors.has(id)
              : searching && !matchSet.has(id);
          const finding = findingMarks?.get(id);
          const label = labels.get(id);
          const activeLabel = id === active;
          const labelWidth = activeLabel
            ? Math.ceil(Math.min(nodeLabel(node).length * 6.6 + 18, 420)) + 2
            : Math.min(nodeLabel(node).length * 6 + 6, 162);
          const labelHeight = activeLabel ? 30 : 16;
          const leader =
            label && (activeLabel || (!node.canonical && node.accesses.length))
              ? {
                  x: Math.max(label.x, Math.min(0, label.x + labelWidth)),
                  y: Math.max(label.y, Math.min(0, label.y + labelHeight)),
                }
              : null;
          return (
            <button
              key={id}
              className={`graph-node ${selected ? 'is-selected' : ''} ${dimmed ? 'is-muted' : ''} ${matchSet.has(id) ? 'is-match' : ''} ${neighbors.has(id) && active !== id ? 'is-neighbor' : ''} ${state.view === 'entries' && !highlighted && !focusPaths.has(id) ? 'is-context' : ''} ${findingPath?.has(id) ? 'is-finding-path' : ''}`}
              data-node-id={id}
              data-kind={node.kind}
              data-canonical={!!node.canonical}
              data-flow-path={!!flow?.paths.has(id)}
              data-flow-terminal={!!flow?.terminals.has(id)}
              data-entry={!!node.groupedRoutes?.length}
              data-finding={finding || 'none'}
              data-effect={effect || 'none'}
              data-access-count={node.accesses.length}
              data-emphasized={highlighted}
              data-world-x={positions.get(id)?.x ?? pose.x}
              data-world-y={positions.get(id)?.y ?? pose.y}
              data-pose-x={pose.x}
              data-pose-y={pose.y}
              data-visible={present}
              data-expanded={branchOpen(graph, state, id)}
              style={{
                left: pose.x,
                top: pose.y,
                opacity: pose.opacity,
                pointerEvents: present ? 'auto' : 'none',
              }}
              tabIndex={present ? 0 : -1}
              aria-label={`Select ${node.name}${node.call ? `, call ${node.call.order}, ${node.range?.file}:${node.range?.startLine}` : `, ${node.range?.file}`}${semanticDescription(node) ? `, ${semanticDescription(node)}` : ''}${finding ? `, has a ${finding}` : ''}`}
              aria-pressed={selected}
              title={`${node.symbol?.qualifiedName || node.call?.qualifiedName || node.name}\n${node.subtitle}\n${semanticDescription(node)}${node.children.length ? '\nDouble-click to open recorded detail' : ''}`}
              onMouseEnter={() => setHovered(id)}
              onMouseLeave={() => setHovered(null)}
              onFocus={() => setHovered(id)}
              onBlur={() => setHovered(null)}
              onClick={() => dispatch({ type: 'select', id })}
              onDoubleClick={() => dispatch({ type: 'toggle', id })}
              onKeyDown={(event) => {
                if (event.key === ' ' && event.shiftKey) {
                  event.preventDefault();
                  dispatch({ type: 'toggle', id });
                }
              }}
            >
              <span className="code-glyph">
                {effect
                  ? effectGlyph(effect)
                  : node.kind === 'route'
                    ? '↗'
                    : node.kind === 'gap'
                      ? '?'
                      : node.kind === 'auth'
                        ? 'a'
                        : node.kind === 'data'
                          ? 'd'
                          : ''}
              </span>
              {effect && node.groupedRoutes?.length && (
                <span className="entry-mark" aria-hidden="true">
                  ↗
                </span>
              )}
              {finding && (
                <span
                  className={`finding-mark ${finding}`}
                  aria-hidden="true"
                />
              )}
              {node.children.length > 0 && (
                <span
                  className={`expansion-dot ${branchOpen(graph, state, id) ? 'is-open' : ''}`}
                />
              )}
              {leader && (
                <span
                  className="label-leader"
                  aria-hidden="true"
                  style={{
                    width: Math.hypot(leader.x, leader.y) / state.camera.scale,
                    transform: `rotate(${Math.atan2(leader.y, leader.x)}rad)`,
                  }}
                />
              )}
              {label && (
                <span
                  className={`node-name ${activeLabel ? 'is-active' : ''}`}
                  style={{
                    left: 13 + label.x / state.camera.scale,
                    top: 13 + label.y / state.camera.scale,
                  }}
                >
                  {nodeLabel(node)}
                </span>
              )}
            </button>
          );
        })}
      </div>
      {captions.length > 0 && (
        <div className="role-captions" aria-label="Layout roles">
          {captions.map((caption) => (
            <div
              key={caption.label}
              style={{
                left: caption.x * state.camera.scale + state.camera.x,
                top: caption.y * state.camera.scale + state.camera.y,
              }}
            >
              <strong>{caption.label}</strong>
              <small>{caption.detail}</small>
            </div>
          ))}
        </div>
      )}
      <div className="canvas-hint">
        Drag to explore <span>·</span> Select an entry to trace data
      </div>
      <div className="camera-controls" aria-label="Graph camera controls">
        <button onClick={() => zoom(1 / 1.15)} aria-label="Zoom out">
          <Minus size={15} />
        </button>
        <output aria-label="Zoom level">
          {Math.round(state.camera.scale * 100)}%
        </output>
        <button onClick={() => zoom(1.15)} aria-label="Zoom in">
          <Plus size={15} />
        </button>
        <span className="control-divider" />
        <button
          disabled={!state.selected}
          aria-label="Bring selected node into view"
          title="Bring selected node into view"
          onClick={() => {
            const { width, height } = size(),
              p = positions.get(state.selected!)!;
            dispatch({
              type: 'camera',
              camera: {
                ...state.camera,
                x: width / 2 - p.x * state.camera.scale,
                y: height / 2 - p.y * state.camera.scale,
              },
            });
          }}
        >
          <LocateFixed size={16} />
        </button>
        <button
          aria-label="Fit visible graph"
          title="Fit visible graph"
          onClick={() => {
            const { width, height } = size();
            dispatch({
              type: 'camera',
              camera: fitCamera(positions, renderedVisible, width, height),
            });
          }}
        >
          <Maximize size={15} />
        </button>
      </div>
    </div>
  );
}
