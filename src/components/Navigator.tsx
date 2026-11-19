import { useMemo, useState } from 'react';
import { ChevronRight, Search } from 'lucide-react';
import { nodeFindingKind, type FindingIndex } from '../graph/findings';
import { compactDir, type ProjectTree, type TreeDir } from '../graph/project';
import type { AtlasGraph, Route } from '../graph/types';

function Filter({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="findings-search rail-filter">
      <Search size={13} />
      <input
        aria-label={label}
        placeholder={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

const coverageComplete = (route: Route) =>
  Object.values(route.budget.coverage).every((axis) => axis === 'complete');

export function EndpointsList({
  graph,
  findings,
  activeEntry,
  activeRoute,
  onOpen,
}: {
  graph: AtlasGraph;
  findings: FindingIndex | null;
  activeEntry: string | null;
  activeRoute: string | null;
  onOpen: (route: Route) => void;
}) {
  const [query, setQuery] = useState('');
  const routes = useMemo(
    () =>
      [...graph.document.routes].sort(
        (a, b) =>
          a.pathTemplate.localeCompare(b.pathTemplate) ||
          a.httpMethod.localeCompare(b.httpMethod),
      ),
    [graph],
  );
  const needle = query.trim().toLowerCase();
  const shown = routes.filter(
    (route) =>
      !needle ||
      `${route.httpMethod} ${route.pathTemplate} ${route.handler.qualifiedName}`
        .toLowerCase()
        .includes(needle),
  );
  const complete = routes.filter(coverageComplete).length;
  return (
    <section className="rail-section rail-list" aria-label="Endpoints">
      <p className="rail-note">
        {routes.length} HTTP routes in {graph.document.frameworks.join(', ')}.{' '}
        {complete} with complete slice coverage.
      </p>
      <Filter label="Filter endpoints" value={query} onChange={setQuery} />
      {!shown.length ? (
        <p className="rail-note">No endpoints match.</p>
      ) : (
        <ul className="endpoint-list">
          {shown.map((route) => {
            const items = findings?.items.filter(
              (item) => item.route.id === route.id,
            );
            const kind = nodeFindingKind(items);
            return (
              <li key={route.id}>
                <button
                  aria-current={
                    (
                      activeRoute
                        ? activeRoute === route.id
                        : activeEntry === route.handler.symbolId
                    )
                      ? 'true'
                      : undefined
                  }
                  onClick={() => onOpen(route)}
                  title={`${route.handler.qualifiedName}\n${route.handler.range.file}:${route.handler.range.startLine}`}
                >
                  <span className={`method ${route.httpMethod.toLowerCase()}`}>
                    {route.httpMethod}
                  </span>
                  <span className="endpoint-copy">
                    <strong>
                      {route.pathTemplate.split('/').map((part, index) => (
                        <span key={index}>
                          {index > 0 && (
                            <>
                              /<wbr />
                            </>
                          )}
                          {part}
                        </span>
                      ))}
                    </strong>
                    <small>
                      {route.handler.qualifiedName.split('.').at(-1)}
                      {!coverageComplete(route) && ' · partial'}
                    </small>
                  </span>
                  {kind && (
                    <span
                      className={`finding-dot ${kind}`}
                      aria-label={`${items!.length} ${kind === 'finding' ? 'finding' : 'candidate'}`}
                    />
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function DirRows({
  dir,
  depth,
  open,
  toggle,
  onOpenFile,
  activeGroup,
}: {
  dir: TreeDir;
  depth: number;
  open: Set<string>;
  toggle: (path: string) => void;
  onOpenFile: (groupId: string) => void;
  activeGroup: string | null;
}) {
  return (
    <>
      {dir.dirs.map((child) => {
        const { label, dir: shown } = compactDir(child);
        const expanded = open.has(shown.path);
        return (
          <li key={shown.path}>
            <button
              className={`tree-row is-dir ${shown.symbols ? 'has-code' : ''}`}
              style={{ paddingLeft: 4 + depth * 12 }}
              aria-expanded={expanded}
              onClick={() => toggle(shown.path)}
              title={shown.path}
            >
              <ChevronRight size={12} className="tree-chevron" />
              <span className="tree-name">{label}</span>
              {shown.findings > 0 && <span className="finding-dot finding" />}
              <small>{shown.fileCount}</small>
            </button>
            {expanded && (
              <ul>
                <DirRows
                  dir={shown}
                  depth={depth + 1}
                  open={open}
                  toggle={toggle}
                  onOpenFile={onOpenFile}
                  activeGroup={activeGroup}
                />
              </ul>
            )}
          </li>
        );
      })}
      {dir.files.map((file) => (
        <li key={file.path}>
          <button
            className={`tree-row is-file ${file.groupId ? 'has-code' : ''}`}
            style={{ paddingLeft: 16 + depth * 12 }}
            disabled={!file.groupId}
            aria-current={
              file.groupId && file.groupId === activeGroup ? 'true' : undefined
            }
            onClick={() => file.groupId && onOpenFile(file.groupId)}
            title={
              file.groupId
                ? `${file.path}\n${file.symbols} indexed symbols${file.endpoints ? ` · ${file.endpoints} endpoints` : ''}`
                : `${file.path}\nNo indexed code in this scan`
            }
          >
            <span className="tree-name">{file.name}</span>
            {file.findings.length > 0 && (
              <span
                className={`finding-dot ${nodeFindingKind(file.findings)}`}
              />
            )}
            {file.endpoints > 0 && (
              <span className="tree-entry">↗{file.endpoints}</span>
            )}
            {file.symbols > 0 && <small>{file.symbols}</small>}
          </button>
        </li>
      ))}
    </>
  );
}

export function FileTree({
  tree,
  total,
  truncated,
  onOpenFile,
  activeGroup,
}: {
  tree: ProjectTree;
  total: number;
  truncated: boolean;
  onOpenFile: (groupId: string) => void;
  activeGroup: string | null;
}) {
  // Folders that hold indexed code start open; the rest of the project stays folded.
  const [open, setOpen] = useState(() => {
    const ids = new Set<string>();
    const visit = (dir: TreeDir) => {
      for (const child of dir.dirs) {
        const { dir: shown } = compactDir(child);
        if (shown.symbols) {
          ids.add(shown.path);
          visit(shown);
        }
      }
    };
    visit(tree.root);
    return ids;
  });
  const [query, setQuery] = useState('');
  const toggle = (path: string) =>
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  const needle = query.trim().toLowerCase();
  const matches = useMemo(() => {
    if (!needle) return [];
    const found: TreeDir['files'] = [];
    const visit = (dir: TreeDir) => {
      found.push(
        ...dir.files.filter((file) => file.path.toLowerCase().includes(needle)),
      );
      dir.dirs.forEach(visit);
    };
    visit(tree.root);
    return found.slice(0, 200);
  }, [tree, needle]);
  return (
    <section className="rail-section rail-list" aria-label="Project files">
      <p className="rail-note">
        {tree.recordedOnly
          ? `${tree.root.fileCount} files named by the scan. This scan has no full file list.`
          : `${total.toLocaleString()} tracked files${truncated ? ` (first ${tree.root.fileCount.toLocaleString()} shown)` : ''}. ${tree.root.symbols} indexed symbols in highlighted files.`}
      </p>
      <Filter label="Find a file" value={query} onChange={setQuery} />
      <ul className="file-tree">
        {needle ? (
          matches.length ? (
            matches.map((file) => (
              <li key={file.path}>
                <button
                  className={`tree-row is-file ${file.groupId ? 'has-code' : ''}`}
                  disabled={!file.groupId}
                  onClick={() => file.groupId && onOpenFile(file.groupId)}
                  title={file.path}
                >
                  <span className="tree-name">{file.path}</span>
                  {file.symbols > 0 && <small>{file.symbols}</small>}
                </button>
              </li>
            ))
          ) : (
            <li className="rail-note">No files match.</li>
          )
        ) : (
          <DirRows
            dir={tree.root}
            depth={0}
            open={open}
            toggle={toggle}
            onOpenFile={onOpenFile}
            activeGroup={activeGroup}
          />
        )}
      </ul>
    </section>
  );
}
