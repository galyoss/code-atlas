import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowUpRight,
  Database,
  FolderTree,
  Maximize2,
  Minus,
  Orbit,
  PanelLeft,
  PanelLeftClose,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Route,
  Search,
  X,
  SlidersHorizontal,
} from 'lucide-react';
import type { AtlasGraph } from '../graph/types';
import { cosmicGraph } from '../graph/cinematic';
import {
  cosmicLayouts,
  filterCosmic,
  type CosmicFilter,
  type CosmicLayout,
} from '../graph/cinematic-controls';
import {
  focusDescription,
  focusVisibility,
  recordedFocus,
  roleStyles,
  semanticRoles,
  serviceEvidence,
} from '../graph/cinematic-semantics';
import { dataEffect, effectLabel } from '../graph/semantics';
import { createUniverse, type UniverseRenderer } from './cinematic-renderer';
import './cinematic.css';

const layouts = [
  {
    id: 'files',
    name: 'Files',
    title: 'File constellation',
    icon: FolderTree,
    note: 'Group nodes by source file',
  },
  {
    id: 'entries',
    name: 'Entry points',
    title: 'Entry points',
    icon: Route,
    note: 'Handlers and implementation',
  },
  {
    id: 'data',
    name: 'Data flow',
    title: 'Data flow',
    icon: Database,
    note: 'Entry → code → data operations',
  },
] as const;
const initialFilter: CosmicFilter = { resolution: 'all', group: '', query: '' };

export default function CinematicGraph({
  graph,
  onExit,
}: {
  graph: AtlasGraph;
  onExit: () => void;
}) {
  const cosmic = useMemo(() => cosmicGraph(graph), [graph]);
  const positions = useMemo(
    () => cosmicLayouts(graph, cosmic),
    [graph, cosmic],
  );
  const groupLabels = useMemo(() => {
    const paths = graph.groups.map((group) => ({
      id: group.id,
      parts: group.file.split('/'),
    }));
    return new Map(
      paths.map(({ id, parts }) => {
        let depth = 2;
        while (
          depth < parts.length &&
          paths.some(
            (other) =>
              other.id !== id &&
              other.parts.slice(-depth).join('/') ===
                parts.slice(-depth).join('/'),
          )
        )
          depth++;
        return [
          id,
          `${parts.at(-1)}${parts.length > 1 ? ` · ${parts.slice(-depth, -1).join('/')}` : ''}`,
        ];
      }),
    );
  }, [graph]);
  const host = useRef<HTMLDivElement>(null),
    engine = useRef<UniverseRenderer | null>(null);
  const section = useRef<HTMLElement>(null),
    railButton = useRef<HTMLButtonElement>(null);
  const [reduced, setReduced] = useState(
    () => window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );
  const [paused, setPaused] = useState(false),
    [error, setError] = useState('');
  const [selected, setSelected] = useState<number | null>(null);
  const [hover, setHover] = useState<{
    index: number;
    x: number;
    y: number;
  } | null>(null);
  const [layout, setLayout] = useState<CosmicLayout>('files');
  const [filter, setFilter] = useState<CosmicFilter>(initialFilter);
  const [railOpen, setRailOpen] = useState(
    () => !window.matchMedia('(max-width: 760px)').matches,
  );
  const baseVisibility = useMemo(
    () => filterCosmic(cosmic, filter),
    [cosmic, filter],
  );
  const focus = useMemo(
    () =>
      selected === null
        ? null
        : recordedFocus(graph, cosmic.nodes[selected].node.id),
    [graph, cosmic, selected],
  );
  const visibility = useMemo(
    () => focusVisibility(cosmic, baseVisibility, focus),
    [cosmic, baseVisibility, focus],
  );
  const presentation = useMemo(
    () => ({ ...visibility, positions: positions[layout], layout, focus }),
    [visibility, positions, layout, focus],
  );
  const roleCounts = useMemo(
    () =>
      new Map(
        semanticRoles.map((role) => [
          role,
          [...visibility.nodes].filter((i) => cosmic.nodes[i].role === role)
            .length,
        ]),
      ),
    [cosmic, visibility],
  );
  const moving = !paused && !reduced;
  const movingRef = useRef(moving);
  movingRef.current = moving;
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const change = () => setReduced(media.matches);
    media.addEventListener('change', change);
    return () => media.removeEventListener('change', change);
  }, []);
  useEffect(() => {
    let renderer: UniverseRenderer | null = null;
    try {
      renderer = createUniverse(
        host.current!,
        cosmic,
        {
          select: setSelected,
          hover: (index, x, y) =>
            setHover(index === null ? null : { index, x, y }),
          error: setError,
        },
        movingRef.current,
      );
      engine.current = renderer;
    } catch {
      setError('This browser could not initialize the 3D renderer.');
    }
    return () => {
      renderer?.dispose();
      engine.current = null;
    };
  }, [cosmic]);
  useEffect(() => {
    engine.current?.setMotion(moving);
  }, [moving]);
  useEffect(() => {
    engine.current?.setPresentation(presentation, !reduced);
    setHover(null);
  }, [presentation, reduced, railOpen]);
  useEffect(() => {
    // Only a filter change clears selection; a click on temporarily revealed evidence is valid.
    setSelected((current) =>
      current !== null && !baseVisibility.nodes.has(current) ? null : current,
    );
  }, [baseVisibility]);
  useEffect(() => {
    engine.current?.select(selected);
  }, [selected]);
  const node = selected === null ? null : cosmic.nodes[selected].node;
  const effect = node ? dataEffect(node) : null;
  const partial = graph.document.routes.some((route) =>
    Object.values(route.budget.coverage).some((axis) => axis !== 'complete'),
  );
  const filtered =
    filter.resolution !== 'all' || !!filter.group || !!filter.query.trim();
  function closeRail() {
    setRailOpen(false);
    requestAnimationFrame(() => railButton.current?.focus());
  }
  function resetFilters() {
    setFilter(initialFilter);
  }
  async function fullScreen() {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await section.current?.requestFullscreen();
    } catch {
      /* Fullscreen is optional; the scene already occupies the viewport. */
    }
  }
  return (
    <section
      ref={section}
      className="universe"
      aria-label="3D code universe"
      data-motion={moving ? 'playing' : 'paused'}
      data-reduced-motion={reduced}
      data-focus-kind={focus?.kind || ''}
      data-focus-count={focus?.paths.size || 0}
      data-focus-terminals={focus?.terminals.size || 0}
      data-revealed={visibility.nodes.size - baseVisibility.nodes.size}
      data-selected={node?.id || ''}
      data-layout={layout}
      data-rail-open={railOpen}
      data-resolution={filter.resolution}
      data-file-filter={filter.group}
      data-query={filter.query}
      onKeyDown={(event) => {
        if ((event.target as HTMLElement).closest('input, select, textarea'))
          return;
        if (event.key === 'Escape' && !document.fullscreenElement) {
          event.stopPropagation();
          if (node) setSelected(null);
          else if (railOpen) closeRail();
          else onExit();
        }
      }}
    >
      {railOpen && (
        <aside
          id="universe-controls"
          className="universe-rail"
          aria-label="3D graph controls"
          onKeyDown={(event) => {
            event.stopPropagation();
            if (event.key === 'Escape') closeRail();
          }}
        >
          <div className="universe-rail-heading">
            <span>
              <SlidersHorizontal size={15} /> Graph controls
            </span>
            <button aria-label="Close 3D graph controls" onClick={closeRail}>
              <PanelLeftClose size={15} />
            </button>
          </div>
          <section className="universe-control-section">
            <h2>Layout</h2>
            <div
              className="universe-layout-options"
              role="group"
              aria-label="3D layout"
            >
              {layouts.map(({ id, name: label, icon: Icon, note }) => (
                <button
                  key={id}
                  aria-pressed={layout === id}
                  onClick={() => setLayout(id)}
                  title={note}
                >
                  <Icon size={15} />
                  <span>{label}</span>
                  <i />
                </button>
              ))}
            </div>
          </section>
          <section className="universe-control-section">
            <h2>Detail</h2>
            <div
              className="universe-detail-options"
              role="group"
              aria-label="3D detail"
            >
              <button
                aria-pressed={filter.resolution === 'all'}
                onClick={() => setFilter({ ...filter, resolution: 'all' })}
              >
                All calls
              </button>
              <button
                aria-pressed={filter.resolution === 'symbols'}
                onClick={() => setFilter({ ...filter, resolution: 'symbols' })}
              >
                Symbols
              </button>
            </div>
            {layout === 'data' && filter.resolution === 'symbols' && (
              <p className="universe-control-note">
                Show All calls to see data operations.
              </p>
            )}
          </section>
          <section className="universe-control-section">
            <label htmlFor="universe-file">File cluster</label>
            <select
              id="universe-file"
              title={
                graph.groups.find((group) => group.id === filter.group)?.file ||
                'All file clusters'
              }
              value={filter.group}
              onChange={(event) =>
                setFilter({ ...filter, group: event.target.value })
              }
            >
              <option value="">All file clusters</option>
              {graph.groups.map((group) => (
                <option value={group.id} key={group.id}>
                  {groupLabels.get(group.id)}
                </option>
              ))}
            </select>
            <label className="universe-search-label" htmlFor="universe-search">
              Find code
            </label>
            <div className="universe-search">
              <Search size={13} />
              <input
                id="universe-search"
                type="search"
                value={filter.query}
                placeholder="Name, route or source…"
                onChange={(event) =>
                  setFilter({ ...filter, query: event.target.value })
                }
              />
            </div>
          </section>
          <div className="universe-filter-summary" aria-live="polite">
            <span>
              {visibility.nodes.size.toLocaleString()} /{' '}
              {cosmic.nodes.length.toLocaleString()} nodes
            </span>
            <button onClick={resetFilters} disabled={!filtered}>
              Clear filters
            </button>
          </div>
          <section className="universe-control-section universe-legend">
            <h2>Code roles</h2>
            <div
              className="universe-semantic-key"
              aria-label="Code role legend"
            >
              {semanticRoles
                .filter((role) => roleCounts.get(role))
                .map((role) => (
                  <span
                    key={role}
                    title={roleStyles[role].description}
                    style={{ color: roleStyles[role].css }}
                  >
                    <i />
                    {roleStyles[role].label}
                    <b>{roleCounts.get(role)?.toLocaleString()}</b>
                  </span>
                ))}
            </div>
          </section>
        </aside>
      )}
      <div className="universe-viewport">
        <div
          className="universe-stage"
          ref={host}
          data-nodes={cosmic.nodes.length}
          data-edges={cosmic.edges.length}
        />
        <div className="universe-vignette" aria-hidden="true" />
        <header className="universe-header">
          <button
            ref={railButton}
            className="universe-rail-toggle"
            aria-label="3D graph controls"
            aria-expanded={railOpen}
            aria-controls="universe-controls"
            onClick={() => setRailOpen(!railOpen)}
          >
            <PanelLeft size={15} />
            <span>Explore</span>
          </button>
          <div className="universe-title">
            <h2>{layouts.find((item) => item.id === layout)!.title}</h2>
            <p>
              {visibility.nodes.size.toLocaleString()} nodes <span>·</span>{' '}
              {visibility.edges.size.toLocaleString()} links
            </p>
          </div>
        </header>
        {!visibility.nodes.size && !error && (
          <div className="universe-empty" role="status">
            <Search size={24} />
            <h2>No code matches these filters.</h2>
            <p>Try another name or restore the full network.</p>
            <button onClick={resetFilters}>
              Clear filters <ArrowUpRight size={15} />
            </button>
          </div>
        )}
        <div className="universe-guide" aria-hidden="true">
          Drag to orbit · Scroll to zoom
        </div>
        {hover && !node && (
          <div
            className="universe-tooltip"
            style={{
              left: Math.max(
                8,
                Math.min(
                  hover.x + 18,
                  (host.current?.clientWidth || 390) - 266,
                ),
              ),
              top: Math.max(
                90,
                Math.min(
                  hover.y - 20,
                  (host.current?.clientHeight || 800) - 180,
                ),
              ),
            }}
          >
            <span>
              {cosmic.nodes[hover.index].node.canonical
                ? 'CODE SYMBOL'
                : 'RECORDED OCCURRENCE'}
            </span>
            <strong>{cosmic.nodes[hover.index].node.name}</strong>
            <small>
              {cosmic.nodes[hover.index].node.range?.file.split('/').at(-1)}
            </small>
          </div>
        )}
        {node && (
          <aside className="universe-detail" aria-label="Selected code node">
            <div className="universe-detail-top">
              <span>
                {node.groupedRoutes?.length
                  ? 'ENTRY POINT'
                  : node.canonical
                    ? 'CODE SYMBOL'
                    : node.kind === 'auth'
                      ? 'AUTH CONTEXT'
                      : 'CALL OCCURRENCE'}
              </span>
              <button
                aria-label="Clear 3D selection"
                onClick={() => setSelected(null)}
              >
                <X size={16} />
              </button>
            </div>
            <h2>
              {node.name}
              <ArrowUpRight size={17} />
            </h2>
            <div
              className="universe-node-role"
              style={{ color: roleStyles[cosmic.nodes[selected!].role].css }}
            >
              <i />
              {roleStyles[cosmic.nodes[selected!].role].label}
            </div>
            {['external', 'unresolved', 'service'].includes(
              cosmic.nodes[selected!].role,
            ) && (
              <small>
                {roleStyles[cosmic.nodes[selected!].role].description}
              </small>
            )}
            {effect && (
              <span className="universe-effect">
                {effectLabel(effect)} data
                {serviceEvidence(node) ? ' · RPC evidence' : ''}
              </span>
            )}
            {focus && (
              <div className="universe-focus-summary" role="status">
                <strong>{focusDescription(focus)}</strong>
                <span>
                  {focus.paths.size.toLocaleString()} path nodes ·{' '}
                  {focus.terminals.size} data terminals
                </span>
                {visibility.nodes.size > baseVisibility.nodes.size && (
                  <span>
                    {visibility.nodes.size - baseVisibility.nodes.size} nodes
                    temporarily revealed · filters retained
                  </span>
                )}
                <small>
                  Arrows show recorded direction. Thin links show code
                  definitions.
                </small>
              </div>
            )}
            <p>
              {node.range?.file}
              {node.range ? `:${node.range.startLine}` : ''}
            </p>
            <small>
              {node.call
                ? `${node.call.resolution} target · static call evidence`
                : node.symbol?.signature || node.subtitle}
            </small>
          </aside>
        )}
        {error && (
          <div className="universe-error" role="alert">
            <Orbit size={32} />
            <h2>3D view unavailable</h2>
            <p>{error}</p>
            <button onClick={onExit}>
              Return to 2D graph <ArrowUpRight size={15} />
            </button>
          </div>
        )}
        <div className="universe-dock" aria-label="3D view controls">
          <button
            className="universe-motion"
            onClick={() => setPaused(!paused)}
            disabled={reduced}
            aria-label={
              reduced
                ? 'Motion disabled by reduced motion preference'
                : paused
                  ? 'Play animation'
                  : 'Pause animation'
            }
            title={reduced ? 'Reduced motion preference is active' : undefined}
          >
            {moving ? <Pause size={16} /> : <Play size={16} />}
            <span>{moving ? 'Pause' : 'Play'}</span>
          </button>
          <i />
          <button
            aria-label="Zoom out"
            onClick={() => engine.current?.zoom(1.18)}
          >
            <Minus size={17} />
          </button>
          <button
            aria-label="Zoom in"
            onClick={() => engine.current?.zoom(0.85)}
          >
            <Plus size={17} />
          </button>
          <button
            aria-label="Reset 3D view"
            onClick={() => {
              engine.current?.reset();
              setSelected(null);
            }}
          >
            <RotateCcw size={16} />
          </button>
          <i className="universe-fullscreen-separator" />
          <button
            className="universe-fullscreen"
            aria-label="Toggle fullscreen"
            onClick={fullScreen}
          >
            <Maximize2 size={16} />
          </button>
        </div>
        <footer className="universe-footer">
          <span>Static graph{partial ? ' · partial route coverage' : ''}</span>
        </footer>
      </div>
    </section>
  );
}
