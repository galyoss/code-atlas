import { DetailAnchors, type NetworkLayout } from './layout';
import { flowIndex } from './flow';
import type { GraphView } from './semantics';
import type { AtlasGraph, Point } from './types';

export interface RoleCaption extends Point {
  label: string;
  detail: string;
}
const SPACING = 40;
/** A band's slots are reserved once, including hidden nodes. Adding detail only
 * allocates unused slots, so surviving identities keep their within-view anchors. */
class SemanticAnchors {
  readonly positions = new Map<string, Point>();
  private counts = new Map<string, number>();
  readonly captions: RoleCaption[];
  constructor(
    private graph: AtlasGraph,
    private view: 'entries' | 'data',
  ) {
    this.captions =
      view === 'data'
        ? [
            {
              x: -554,
              y: -408,
              label: '01 / ENTRY POINTS',
              detail: 'HTTP handlers',
            },
            {
              x: -110,
              y: -408,
              label: '02 / CODE & CALLS',
              detail: 'Recorded paths · definition context',
            },
            {
              x: 488,
              y: -408,
              label: '03 / DATA OPERATIONS',
              detail: 'Reads · writes · named objects',
            },
          ]
        : [
            {
              x: -348,
              y: -408,
              label: '01 / ENTRY POINTS',
              detail: 'Select a handler to trace its data paths',
            },
            {
              x: 368,
              y: -408,
              label: '02 / IMPLEMENTATION',
              detail: 'Code symbols & recorded calls',
            },
          ];
    for (const id of graph.baseIds) this.place(id);
    // Files are an alternate resolution. Their buttons occupy a separate row,
    // and expanded source regions fade away in semantic layouts.
    graph.groups.forEach((group, index) =>
      this.positions.set(group.id, {
        x: -570 + (index % 7) * 180,
        y: -286 + Math.floor(index / 7) * 80,
      }),
    );
    // Reserve overview detail independently of which view/entry is visited first.
    if (view === 'data') this.ensure(flowIndex(graph).overview.paths);
  }
  private place(id: string) {
    if (this.positions.has(id)) return;
    const node = this.graph.nodes.get(id)!;
    if (node.kind === 'group') return;
    const entry = !!node.groupedRoutes?.length;
    const terminal = !node.canonical && flowIndex(this.graph).terminals.has(id);
    const band = entry
      ? 'entry'
      : this.view === 'data' && terminal
        ? 'data'
        : 'code';
    const index = this.counts.get(band) || 0;
    this.counts.set(band, index + 1);
    const rows = 14;
    // Column-major slots keep expansions within a band; additional columns grow
    // down in pages instead of crossing another role's horizontal boundary.
    const columns =
      this.view === 'data'
        ? band === 'entry'
          ? 5
          : band === 'data'
            ? 10
            : 17
        : band === 'entry'
          ? 7
          : 15;
    const page = Math.floor(index / (rows * columns));
    const slot = index % (rows * columns);
    const x =
      this.view === 'data'
        ? band === 'entry'
          ? -608
          : band === 'data'
            ? 362
            : -374
        : band === 'entry'
          ? -500
          : 116;
    this.positions.set(id, {
      x: x + Math.floor(slot / rows) * SPACING,
      y: -306 + (slot % rows) * SPACING + page * (rows + 2) * SPACING,
    });
  }
  ensure(ids: ReadonlySet<string>) {
    // Producer order provides deterministic tie-breaking without names/keywords.
    for (const id of ids) this.place(id);
    return this.positions;
  }
}
export class ViewAnchors {
  private code: DetailAnchors;
  private semantic: Record<'entries' | 'data', SemanticAnchors>;
  constructor(
    private graph: AtlasGraph,
    layout: NetworkLayout,
  ) {
    this.code = new DetailAnchors(layout);
    this.semantic = {
      entries: new SemanticAnchors(graph, 'entries'),
      data: new SemanticAnchors(graph, 'data'),
    };
  }
  ensure(view: GraphView, visible: ReadonlySet<string>) {
    // A fresh map tells the motion hook when appended targets change, while all
    // stored point objects and anchors remain intact across view round trips.
    return new Map(
      view === 'code'
        ? this.code.ensure(this.graph, visible)
        : this.semantic[view].ensure(visible),
    );
  }
  captions(view: GraphView) {
    return view === 'code' ? [] : this.semantic[view].captions;
  }
}
