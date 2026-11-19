import { groupNodeId } from './adapter';
import type { FindingIndex, FindingItem } from './findings';
import type { AtlasGraph } from './types';

export interface TreeFile {
  name: string;
  path: string;
  /** The graph's source-file group, when the scan indexed code in this file. */
  groupId?: string;
  symbols: number;
  endpoints: number;
  findings: FindingItem[];
}
export interface TreeDir {
  name: string;
  path: string;
  dirs: TreeDir[];
  files: TreeFile[];
  fileCount: number;
  symbols: number;
  endpoints: number;
  findings: number;
}
export interface ProjectTree {
  root: TreeDir;
  /** Without a recorded manifest, the tree holds only files the graph names. */
  recordedOnly: boolean;
}

/** Combine the checkout's tracked paths with what the graph recorded about each file. */
export function projectTree(
  graph: AtlasGraph,
  paths: string[] | null,
  findings: FindingIndex | null,
): ProjectTree {
  const groups = new Map(graph.groups.map((group) => [group.file, group]));
  const endpoints = new Map<string, number>();
  for (const route of graph.document.routes)
    endpoints.set(
      route.handler.range.file,
      (endpoints.get(route.handler.range.file) || 0) + 1,
    );
  const byFile = new Map<string, FindingItem[]>();
  for (const item of findings?.items || [])
    for (const file of new Set([
      item.route.handler.range.file,
      item.evidence?.range.file,
    ]))
      if (file) byFile.set(file, [...(byFile.get(file) || []), item]);
  const recordedOnly = !paths;
  const all = new Set(paths || [...groups.keys(), ...endpoints.keys()]);
  const root: TreeDir = {
    name: '',
    path: '',
    dirs: [],
    files: [],
    fileCount: 0,
    symbols: 0,
    endpoints: 0,
    findings: 0,
  };
  for (const path of [...all].sort()) {
    const parts = path.split('/');
    let dir = root;
    const trail = [root];
    for (const part of parts.slice(0, -1)) {
      let next = dir.dirs.find((child) => child.name === part);
      if (!next) {
        next = {
          name: part,
          path: dir.path ? `${dir.path}/${part}` : part,
          dirs: [],
          files: [],
          fileCount: 0,
          symbols: 0,
          endpoints: 0,
          findings: 0,
        };
        dir.dirs.push(next);
      }
      dir = next;
      trail.push(dir);
    }
    const group = groups.get(path);
    const file: TreeFile = {
      name: parts.at(-1)!,
      path,
      groupId: group ? groupNodeId(path) : undefined,
      symbols: group?.members.length || 0,
      endpoints: endpoints.get(path) || 0,
      findings: byFile.get(path) || [],
    };
    dir.files.push(file);
    for (const ancestor of trail) {
      ancestor.fileCount++;
      ancestor.symbols += file.symbols;
      ancestor.endpoints += file.endpoints;
      ancestor.findings += file.findings.length;
    }
  }
  const sort = (dir: TreeDir) => {
    dir.dirs.sort((a, b) => a.name.localeCompare(b.name));
    dir.files.sort((a, b) => a.name.localeCompare(b.name));
    dir.dirs.forEach(sort);
  };
  sort(root);
  return { root, recordedOnly };
}

/** A chain of single-directory folders reads as one row, like an IDE's compact tree. */
export function compactDir(dir: TreeDir): { label: string; dir: TreeDir } {
  let label = dir.name,
    current = dir;
  while (current.dirs.length === 1 && !current.files.length) {
    current = current.dirs[0];
    label += `/${current.name}`;
  }
  return { label, dir: current };
}
