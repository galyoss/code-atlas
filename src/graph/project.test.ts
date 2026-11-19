import { describe, expect, it } from 'vitest';
import raw from '../../docs/scans/aegra-v0.11.0.graph.json';
import type { Vote } from '../api';
import { adaptGraph, groupNodeId } from './adapter';
import { indexFindings } from './findings';
import { compactDir, projectTree, type TreeDir } from './project';
import type { GraphDocument } from './types';

const document = raw as GraphDocument;
const graph = adaptGraph(document);
const files = (dir: TreeDir): string[] => [
  ...dir.files.map((file) => file.path),
  ...dir.dirs.flatMap(files),
];
const find = (
  dir: TreeDir,
  path: string,
): TreeDir['files'][number] | undefined =>
  dir.files.find((file) => file.path === path) ||
  dir.dirs.map((child) => find(child, path)).find(Boolean);

describe('project tree', () => {
  const indexed = graph.groups.map((group) => group.file);
  const manifest = [
    ...indexed,
    'README.md',
    'docs/guide.md',
    'libs/other/x.py',
  ];

  it('holds every tracked path and marks the files with indexed code', () => {
    const { root, recordedOnly } = projectTree(graph, manifest, null);
    expect(recordedOnly).toBe(false);
    expect(files(root).sort()).toEqual([...new Set(manifest)].sort());
    expect(root.fileCount).toBe(new Set(manifest).size);
    expect(root.symbols).toBe(document.symbolIndex.length);
    expect(root.endpoints).toBe(document.routes.length);
    const readme = find(root, 'README.md')!;
    expect(readme.groupId).toBeUndefined();
    const group = graph.groups[0];
    expect(find(root, group.file)!.groupId).toBe(groupNodeId(group.file));
    expect(find(root, group.file)!.symbols).toBe(group.members.length);
  });

  it('falls back to files the graph names, and says so', () => {
    const { root, recordedOnly } = projectTree(graph, null, null);
    expect(recordedOnly).toBe(true);
    expect(new Set(files(root))).toEqual(
      new Set([
        ...indexed,
        ...document.routes.map((route) => route.handler.range.file),
      ]),
    );
  });

  it('attributes a finding to its handler file and its folders', () => {
    const route = document.routes[0];
    const votes: Vote[] = [
      {
        id: 'v0',
        check: 'idor',
        routeId: route.id,
        role: 'hunter',
        verdict: 'present',
        reason: 'r',
      },
    ];
    const index = indexFindings(graph, [], votes, 2);
    const { root } = projectTree(graph, manifest, index);
    expect(find(root, route.handler.range.file)!.findings).toHaveLength(1);
    expect(root.findings).toBe(1);
  });

  it('compacts single-child folder chains', () => {
    const { root } = projectTree(
      graph,
      ['a/b/c/file.py', 'a/b/c/other.py'],
      null,
    );
    const { label, dir } = compactDir(root.dirs[0]);
    expect(label).toBe('a/b/c');
    expect(dir.files.map((file) => file.name)).toEqual(['file.py', 'other.py']);
  });
});
