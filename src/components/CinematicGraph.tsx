import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, ArrowUpRight, Maximize2, Minus, Orbit, Pause, Play, Plus, RotateCcw, X, Zap } from 'lucide-react';
import type { AtlasGraph } from '../graph/types';
import { cosmicGraph } from '../graph/cinematic';
import { dataEffect, effectLabel } from '../graph/semantics';
import { createUniverse, type UniverseRenderer } from './cinematic-renderer';
import './cinematic.css';

export default function CinematicGraph({ graph, name, tag, onExit }: { graph: AtlasGraph; name: string; tag: string; onExit: () => void }) {
  const cosmic = useMemo(() => cosmicGraph(graph), [graph]);
  const host = useRef<HTMLDivElement>(null), engine = useRef<UniverseRenderer | null>(null), section = useRef<HTMLElement>(null);
  const [reduced, setReduced] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const [paused, setPaused] = useState(false), [error, setError] = useState('');
  const [selected, setSelected] = useState<number | null>(null);
  const [hover, setHover] = useState<{ index: number; x: number; y: number } | null>(null);
  const moving = !paused && !reduced;
  const movingRef = useRef(moving); movingRef.current = moving;
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const change = () => setReduced(media.matches);
    media.addEventListener('change', change); return () => media.removeEventListener('change', change);
  }, []);
  useEffect(() => {
    let renderer: UniverseRenderer | null = null;
    try {
      renderer = createUniverse(host.current!, cosmic, {
        select: setSelected,
        hover: (index, x, y) => setHover(index === null ? null : { index, x, y }),
        error: setError,
      }, movingRef.current);
      engine.current = renderer;
    } catch {
      setError('This browser could not open the 3D universe. The full 2D graph is still available.');
    }
    return () => { renderer?.dispose(); engine.current = null; };
  }, [cosmic]);
  useEffect(() => { engine.current?.setMotion(moving); }, [moving]);
  useEffect(() => { engine.current?.select(selected); }, [selected]);
  useEffect(() => { section.current?.querySelector<HTMLButtonElement>('.universe-back')?.focus(); }, []);
  const node = selected === null ? null : cosmic.nodes[selected].node;
  const effect = node ? dataEffect(node) : null;
  const calls = cosmic.nodes.filter(({ node }) => !!node.call).length;
  const partial = graph.document.routes.filter((route) => Object.values(route.budget.coverage).includes('partial')).length;
  async function fullScreen() {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await section.current?.requestFullscreen();
    } catch { /* Fullscreen is optional; the scene already occupies the viewport. */ }
  }
  return (
    <section ref={section} className="universe" aria-label="3D code universe" data-motion={moving ? 'playing' : 'paused'} data-reduced-motion={reduced} data-selected={node?.id || ''} onKeyDown={(event) => {
      if (event.key === 'Escape' && !document.fullscreenElement) { event.stopPropagation(); if (node) setSelected(null); else onExit(); }
    }}>
      <div className="universe-stage" ref={host} data-nodes={cosmic.nodes.length} data-edges={cosmic.edges.length} />
      <div className="universe-vignette" aria-hidden="true" />
      <header className="universe-header">
        <button className="universe-back" onClick={onExit}><ArrowLeft size={15} /> <span>2D graph</span></button>
        <div className="universe-wordmark"><Orbit size={21} strokeWidth={1.3} /><span>CodeAtlas</span><span className="universe-mode">UNIVERSE</span></div>
        <div className="universe-status"><i /><span>{moving ? 'ENERGY IN MOTION' : 'MOTION PAUSED'}</span></div>
      </header>
      <div className="universe-title">
        <div className="universe-eyebrow">THE SHAPE OF YOUR CODE</div>
        <h1>{name}<span>.</span></h1>
        <p>{tag} <span>/</span> {graph.document.repo.revision.slice(0, 7)}</p>
      </div>
      <div className="universe-index" aria-label="Real graph scope">
        <span className="universe-index-line" />
        <strong>{cosmic.nodes.length.toLocaleString()}</strong><span>RECORDED NODES</span>
        <p>{graph.baseIds.length} symbols <b>·</b> {calls.toLocaleString()} call occurrences</p>
        <p>{cosmic.edges.length.toLocaleString()} recorded relationships <b>·</b> {cosmic.clusters.length} files</p>
      </div>
      <div className="universe-guide" aria-hidden="true"><span>DRAG TO ORBIT</span><i /><span>SCROLL TO EXPLORE</span></div>
      {hover && !node && <div className="universe-tooltip" style={{ left: Math.min(hover.x + 18, Math.max(12, (host.current?.clientWidth || 390) - 270)), top: Math.max(90, Math.min(hover.y - 20, (host.current?.clientHeight || 800) - 180)) }}>
        <span>{cosmic.nodes[hover.index].node.canonical ? 'CODE SYMBOL' : 'RECORDED OCCURRENCE'}</span>
        <strong>{cosmic.nodes[hover.index].node.name}</strong>
        <small>{cosmic.nodes[hover.index].node.range?.file.split('/').at(-1)}</small>
      </div>}
      {node && <aside className="universe-detail" aria-label="Selected code node">
        <div className="universe-detail-top"><span>{node.groupedRoutes?.length ? 'ENTRY POINT' : node.canonical ? 'CODE SYMBOL' : node.kind === 'auth' ? 'AUTH CONTEXT' : 'CALL OCCURRENCE'}</span><button aria-label="Clear 3D selection" onClick={() => setSelected(null)}><X size={16} /></button></div>
        <h2>{node.name}<ArrowUpRight size={17} /></h2>
        {effect && <span className="universe-effect">{effectLabel(effect)} data</span>}
        <p>{node.range?.file}{node.range ? `:${node.range.startLine}` : ''}</p>
        <small>{node.call ? `${node.call.resolution} target · static call evidence` : node.symbol?.signature || node.subtitle}</small>
      </aside>}
      {error && <div className="universe-error" role="alert"><Orbit size={32} /><h2>The universe is taking a break.</h2><p>{error}</p><button onClick={onExit}>Return to 2D graph <ArrowUpRight size={15} /></button></div>}
      <div className="universe-dock" aria-label="3D view controls">
        <div className="universe-dock-label"><Zap size={14} /><span>CINEMATIC</span></div>
        <button className="universe-motion" onClick={() => setPaused(!paused)} disabled={reduced} aria-label={reduced ? 'Motion disabled by reduced motion preference' : paused ? 'Play animation' : 'Pause animation'} title={reduced ? 'Reduced motion preference is active' : undefined}>{moving ? <Pause size={16} /> : <Play size={16} />}<span>{moving ? 'Pause' : 'Play'}</span></button>
        <i />
        <button aria-label="Zoom out" onClick={() => engine.current?.zoom(1.18)}><Minus size={17} /></button>
        <button aria-label="Zoom in" onClick={() => engine.current?.zoom(.85)}><Plus size={17} /></button>
        <button aria-label="Reset 3D view" onClick={() => { engine.current?.reset(); setSelected(null); }}><RotateCcw size={16} /></button>
        <i className="universe-fullscreen-separator" />
        <button className="universe-fullscreen" aria-label="Toggle fullscreen" onClick={fullScreen}><Maximize2 size={16} /></button>
      </div>
      <footer className="universe-footer"><span><i className="universe-dot entry" />Entry<i className="universe-dot code" />Code<i className="universe-dot data" />Data</span><span>Illustrative energy · static scan{partial > 0 ? ' · partial coverage' : ''}</span><span className="universe-coordinate">3D / PERSPECTIVE</span></footer>
    </section>
  );
}
