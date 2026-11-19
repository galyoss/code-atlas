import { useMemo, useState } from 'react';
import {
  ArrowDownToLine,
  ArrowUpRight,
  ListFilter,
  Route as RouteIcon,
  Search,
  Shield,
} from 'lucide-react';
import type { AtlasGraph } from '../graph/types';
import type { FindingIndex } from '../graph/findings';
import { sourceIdentity, type ScanSource } from '../source';
import type { TraceTarget } from '../ProjectReport';
import { FindingsList } from './FindingsPanel';

export function ReportLists({
  graph,
  source,
  findings,
  view,
  onInspect,
}: {
  graph: AtlasGraph;
  source: ScanSource;
  findings: FindingIndex | null;
  view: 'routes' | 'issues';
  onInspect: (target: TraceTarget) => void;
}) {
  const [query, setQuery] = useState('');
  const [method, setMethod] = useState('');
  const [coverage, setCoverage] = useState('');
  const routes = useMemo(
    () =>
      [...graph.document.routes].sort(
        (a, b) =>
          a.pathTemplate.localeCompare(b.pathTemplate) ||
          a.httpMethod.localeCompare(b.httpMethod),
      ),
    [graph],
  );
  const methods = [...new Set(routes.map((route) => route.httpMethod))].sort();
  const needle = query.trim().toLowerCase();
  const shown = routes.filter((route) => {
    const complete = Object.values(route.budget.coverage).every(
      (axis) => axis === 'complete',
    );
    return (
      (!method || route.httpMethod === method) &&
      (!coverage || coverage === (complete ? 'complete' : 'limited')) &&
      (!needle ||
        `${route.httpMethod} ${route.pathTemplate} ${route.handler.qualifiedName} ${route.handler.range.file}`
          .toLowerCase()
          .includes(needle))
    );
  });
  const identity = sourceIdentity(source);
  const scan = source.kind === 'api' ? source.scan : null;
  const hasRecords =
    !!scan && (scan.findings.length > 0 || scan.votes.length > 0);
  const issueView = view === 'issues';
  return (
    <section
      className="report-list-layout"
      aria-label={issueView ? 'Issues found' : 'Routes'}
    >
      <aside
        className="report-list-rail"
        aria-label={issueView ? 'Review coverage' : 'Route filters'}
      >
        <h2>
          {issueView ? <Shield size={15} /> : <ListFilter size={15} />}
          {issueView ? 'Review coverage' : 'Route filters'}
        </h2>
        {!issueView && (
          <div className="report-filter-fields">
            <label>
              Find route
              <span className="report-input">
                <Search size={14} />
                <input
                  value={query}
                  placeholder="Path, handler or file…"
                  onChange={(event) => setQuery(event.target.value)}
                />
              </span>
            </label>
            <label>
              HTTP method
              <select
                value={method}
                onChange={(event) => setMethod(event.target.value)}
              >
                <option value="">All methods</option>
                {methods.map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
            </label>
            <label>
              Slice coverage
              <select
                value={coverage}
                onChange={(event) => setCoverage(event.target.value)}
              >
                <option value="">All routes</option>
                <option value="complete">Complete</option>
                <option value="limited">Limited</option>
              </select>
            </label>
          </div>
        )}
        <dl className="report-facts">
          <dt>Revision</dt>
          <dd title={graph.document.repo.revision}>
            {graph.document.repo.revision.slice(0, 7)}
          </dd>
          <dt>HTTP routes</dt>
          <dd>{routes.length.toLocaleString()}</dd>
          {issueView && (
            <>
              <dt>Routes with votes</dt>
              <dd>{findings?.reviewedRoutes ?? 0}</dd>
            </>
          )}
        </dl>
        <a
          className="report-download"
          download={identity.download}
          href={identity.graphUrl}
        >
          <ArrowDownToLine size={13} /> Graph JSON
        </a>
      </aside>
      <div className="report-list-main">
        <header className="report-list-heading">
          <h2>{issueView ? 'Issues found' : 'Routes'}</h2>
          <span>
            {issueView
              ? `${findings?.items.length ?? 0} recorded`
              : `${shown.length} of ${routes.length}`}
          </span>
        </header>
        {issueView ? (
          hasRecords && scan && findings ? (
            <FindingsList
              graph={graph}
              index={findings}
              scan={scan}
              focusedId={null}
              onFocus={(item) =>
                onInspect({
                  routeId: item.route.id,
                  handlerId: item.handlerId,
                  findingId: item.id,
                })
              }
            />
          ) : (
            <div className="report-empty">
              <Shield size={24} strokeWidth={1.4} />
              <h3>No security review recorded</h3>
              <p>
                This revision contains a static code graph. It has no saved
                findings or reviewer votes.
              </p>
            </div>
          )
        ) : shown.length ? (
          <ul className="report-route-list">
            {shown.map((route) => (
              <li key={route.id}>
                <button
                  onClick={() =>
                    onInspect({
                      routeId: route.id,
                      handlerId: route.handler.symbolId,
                    })
                  }
                  aria-label={`Open 2D trace for ${route.httpMethod} ${route.pathTemplate}`}
                >
                  <span
                    className={`report-method method ${route.httpMethod.toLowerCase()}`}
                  >
                    {route.httpMethod}
                  </span>
                  <span className="report-route-copy">
                    <strong>{route.pathTemplate}</strong>
                    <small>{route.handler.qualifiedName}</small>
                  </span>
                  <span
                    className="report-route-source"
                    title={route.handler.range.file}
                  >
                    {route.handler.range.file.split('/').at(-1)}
                    <small>Line {route.handler.range.startLine}</small>
                  </span>
                  <ArrowUpRight size={15} />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <div className="report-empty">
            <RouteIcon size={24} strokeWidth={1.4} />
            <h3>
              {routes.length ? 'No matching routes' : 'No HTTP routes recorded'}
            </h3>
            <p>
              {routes.length
                ? 'Try another filter to see more routes.'
                : 'The scanner recorded no HTTP route handlers for this revision.'}
            </p>
            {routes.length > 0 && (
              <button
                className="report-link"
                onClick={() => {
                  setMethod('');
                  setCoverage('');
                  setQuery('');
                }}
              >
                Clear filters
              </button>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
