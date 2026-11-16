import { describe, expect, it } from 'vitest';
import raw from '../../docs/scans/aegra-v0.11.0.graph.json';
import type { GraphDocument } from './types';
import { adaptGraph, visibleIds } from './adapter';
import { DetailAnchors, initialCamera, layoutGraph } from './layout';
import { initialNavigation, navigate } from './navigation';
import { placeLabels } from './labels';

const graph = adaptGraph(raw as GraphDocument);
describe('active label collision regression', () => {
  it.each([false, true])(
    'keeps the selected label off glyphs after access reveal (other branch open: %s)',
    (manualBranch) => {
      const layout = layoutGraph(graph),
        anchors = new DetailAnchors(layout);
      const camera = initialCamera(layout, graph, 1440, 802);
      let state = initialNavigation();
      if (manualBranch) {
        state = navigate(graph, state, {
          type: 'toggle',
          id: 'sym_get_thread',
        });
        anchors.ensure(
          graph,
          visibleIds(graph, state.expanded, state.collapsed, state.revealed),
        );
      }
      state = navigate(graph, state, {
        type: 'accesses',
        id: 'sym_prepare_run',
      });
      const visible = visibleIds(
        graph,
        state.expanded,
        state.collapsed,
        state.revealed,
      );
      const positions = anchors.ensure(graph, visible);
      const labels = placeLabels(
        graph,
        positions,
        visible,
        [...visible],
        camera.scale,
        'sym_prepare_run',
      );
      const offset = labels.get('sym_prepare_run');
      expect(offset).toBeDefined();
      const anchor = positions.get('sym_prepare_run')!;
      // Actual text box measured by the independent browser gate at the bundled font.
      const rect = {
        x: anchor.x * camera.scale + offset!.x,
        y: anchor.y * camera.scale + offset!.y,
        width: 97.203125,
        height: 28.5,
      };
      const collisions = [...visible].filter((id) => {
        if (graph.nodes.get(id)!.kind === 'group') return false;
        const point = positions.get(id)!,
          radius = 13 * camera.scale;
        return (
          rect.x < point.x * camera.scale + radius &&
          rect.x + rect.width > point.x * camera.scale - radius &&
          rect.y < point.y * camera.scale + radius &&
          rect.y + rect.height > point.y * camera.scale - radius
        );
      });
      expect(collisions).toEqual([]);
    },
  );
});
