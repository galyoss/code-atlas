import {
  useLayoutEffect,
  useRef,
  useState,
  type Dispatch,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
} from 'react';
import { LocateFixed, Maximize, Minus, Plus } from 'lucide-react';
import { fitCamera, NODE_HEIGHT, NODE_WIDTH, zoomCamera } from '../graph/layout';
import type { AtlasGraph, Point } from '../graph/types';
import type { NavigationAction, NavigationState } from '../graph/navigation';
import { useAnimatedScene } from '../hooks/useAnimatedScene';

interface Props {
  graph: AtlasGraph;
  positions: Map<string, Point>;
  visible: Set<string>;
  state: NavigationState;
  dispatch: Dispatch<NavigationAction>;
  onToggle: (id: string) => void;
  children?: ReactNode;
}
export function GraphCanvas({ graph, positions, visible, state, dispatch, onToggle, children }: Props) {
  const viewport = useRef<HTMLDivElement>(null);
  const drag = useRef<{ id: number; origin: Point; camera: Point } | null>(null);
  const [dragging, setDragging] = useState(false);
  const [viewportSize, setViewportSize] = useState({ width: 0, height: 0 });
  const { poses, transitioning } = useAnimatedScene(graph, positions, visible, state.path, state.selected);
  useLayoutEffect(() => {
    const element = viewport.current!;
    const measure = () =>
      setViewportSize({
        width: element.clientWidth,
        height: element.clientHeight,
      });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const hasOffscreenNodes =
    viewportSize.width > 0 &&
    [...visible].some((id) => {
      const position = positions.get(id)!;
      const left = position.x * state.camera.scale + state.camera.x;
      const top = position.y * state.camera.scale + state.camera.y;
      return (
        left < 0 ||
        top < 0 ||
        left + NODE_WIDTH * state.camera.scale > viewportSize.width ||
        top + NODE_HEIGHT * state.camera.scale > viewportSize.height
      );
    });
  const size = () => ({
    width: viewport.current!.clientWidth,
    height: viewport.current!.clientHeight,
  });
  const zoom = (factor: number) => {
    const { width, height } = size();
    dispatch({
      type: 'camera',
      camera: zoomCamera(state.camera, factor, { x: width / 2, y: height / 2 }),
    });
  };
  const focusSelection = () => {
    const { width, height } = size();
    const point = positions.get(state.selected)!;
    dispatch({
      type: 'camera',
      camera: {
        ...state.camera,
        x: width / 2 - (point.x + NODE_WIDTH / 2) * state.camera.scale,
        y: height / 2 - (point.y + NODE_HEIGHT / 2) * state.camera.scale,
      },
    });
  };
  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || (event.target as HTMLElement).closest('button, aside, a')) return;
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
      aria-label="Code graph. Drag or use arrow keys to pan. Plus and minus zoom."
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
      data-transitioning={transitioning}
    >
      <div className="graph-surface">
        <div
          className="graph-world"
          style={{
            transform: `translate(${state.camera.x}px, ${state.camera.y}px) scale(${state.camera.scale})`,
          }}
          data-pan-x={state.camera.x}
          data-pan-y={state.camera.y}
          data-zoom={state.camera.scale}
        >
          <svg className="graph-edges" aria-hidden="true">
            <defs>
              <marker
                id="call-direction"
                markerWidth="8"
                markerHeight="8"
                refX="12"
                refY="4"
                orient="auto"
                markerUnits="userSpaceOnUse"
              >
                <path d="M1 1 L6 4 L1 7" fill="none" stroke="currentColor" strokeWidth="1.2" />
              </marker>
            </defs>
            {graph.edges.map((edge) => {
              const from = poses.get(edge.from);
              const to = poses.get(edge.to);
              if (!from || !to) return null;
              const structural = edge.kind === 'contains';
              const x1 =
                  from.x + (structural ? NODE_WIDTH / 2 : edge.kind === 'context' ? 7 : NODE_WIDTH - 6),
                y1 = from.y + (structural ? NODE_HEIGHT : NODE_HEIGHT / 2);
              const x2 = to.x + (structural ? NODE_WIDTH / 2 : 7),
                y2 = to.y + NODE_HEIGHT / 2;
              const distance = x2 - x1;
              return (
                <path
                  key={edge.id}
                  data-edge-id={edge.id}
                  className={`graph-edge ${edge.kind}`}
                  style={{
                    opacity:
                      Math.min(from.opacity, to.opacity) *
                      (edge.kind === 'summary' && state.path.length ? 0.4 : 0.7),
                  }}
                  d={
                    structural
                      ? `M ${x1} ${y1} V ${y1 + 40} H ${to.x - 24} V ${y2} H ${to.x + 7}`
                      : `M ${x1} ${y1} C ${x1 + distance * 0.45} ${y1}, ${x2 - distance * 0.35} ${y2}, ${x2} ${y2}`
                  }
                />
              );
            })}
          </svg>
          {[...poses].map(([id, pose]) => {
            const node = graph.nodes.get(id)!;
            const shown = visible.has(id);
            const open = state.path.includes(id);
            return (
              <div
                key={id}
                className={`graph-node ${state.selected === id ? 'is-selected' : ''} ${open ? 'is-open' : ''}`}
                data-node-id={id}
                data-call-id={node.call?.id}
                data-kind={node.kind}
                data-world-x={positions.get(id)!.x}
                data-world-y={positions.get(id)!.y}
                aria-hidden={!shown}
                inert={!shown}
                style={{
                  transform: `translate(${pose.x}px, ${pose.y}px)`,
                  opacity: pose.opacity,
                  pointerEvents: shown ? undefined : 'none',
                }}
              >
                <button
                  className="node-main"
                  aria-label={`Select ${node.name}${node.call ? `, call ${node.call.order}, ${node.range?.file}:${node.range?.startLine}` : ''}`}
                  aria-pressed={state.selected === id}
                  title={`${node.name}\n${node.subtitle}`}
                  onClick={() => dispatch({ type: 'select', id })}
                >
                  <span className="node-pin" aria-hidden="true" />
                  <strong>{node.name}</strong>
                  <small>{node.subtitle}</small>
                </button>
                {(node.children.length > 0 || node.groupedRoutes) && (
                  <button
                    className="node-toggle"
                    onClick={() => onToggle(id)}
                    aria-label={
                      node.groupedRoutes
                        ? `Browse ${node.groupedRoutes.length} routes in ${node.name}`
                        : `${open ? 'Collapse' : 'Expand'} ${node.name}${node.call ? `, call ${node.call.order}` : ''}, ${node.children.length} direct calls`
                    }
                    aria-expanded={node.groupedRoutes ? undefined : open}
                    title={
                      node.groupedRoutes
                        ? `Browse ${node.groupedRoutes.length} routes`
                        : `${open ? 'Collapse' : 'Expand'} ${node.children.length} direct calls`
                    }
                  >
                    {node.groupedRoutes ? (
                      <span>↗</span>
                    ) : open ? (
                      <Minus size={14} />
                    ) : (
                      <span>+{node.children.length}</span>
                    )}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>
      <span className={`canvas-hint${hasOffscreenNodes ? ' is-offscreen' : ''}`}>
        {hasOffscreenNodes ? (
          <>
            Some nodes are offscreen <span>·</span> drag to explore
          </>
        ) : (
          <>
            Drag to explore <span>·</span> zoom keeps the same detail
          </>
        )}
      </span>
      <div className="camera-controls" aria-label="Graph camera controls">
        <button
          onClick={() => zoom(1 / 1.15)}
          disabled={state.camera.scale <= 0.45}
          aria-label="Zoom out"
          title="Zoom out"
        >
          <Minus size={16} />
        </button>
        <output aria-label="Zoom level">{Math.round(state.camera.scale * 100)}%</output>
        <button
          onClick={() => zoom(1.15)}
          disabled={state.camera.scale >= 1.8}
          aria-label="Zoom in"
          title="Zoom in"
        >
          <Plus size={16} />
        </button>
        <span className="control-divider" />
        <button
          onClick={focusSelection}
          aria-label="Bring selected node into view"
          title="Bring selection into view"
        >
          <LocateFixed size={17} />
        </button>
        <button
          onClick={() => {
            const { width, height } = size();
            dispatch({
              type: 'camera',
              camera: fitCamera(positions, visible, width, height),
            });
          }}
          aria-label="Fit visible graph"
          title="Fit visible graph"
        >
          <Maximize size={16} />
        </button>
      </div>
      {children}
    </div>
  );
}
