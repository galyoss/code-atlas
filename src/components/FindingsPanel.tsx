import { useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import { Search, X } from 'lucide-react';
import type { ScanSummary } from '../api';
import {
  checkName,
  type FindingIndex,
  type FindingItem,
} from '../graph/findings';
import type { AtlasGraph } from '../graph/types';
import { Excerpt } from './SourcePanel';

type Filter = 'all' | 'finding' | 'candidate';

const statusText = (item: FindingItem) =>
  item.kind === 'finding'
    ? `Finding · ${item.presentCount} supporting ${item.presentCount === 1 ? 'vote' : 'votes'} recorded`
    : `Candidate · ${item.presentCount} supporting ${item.presentCount === 1 ? 'vote' : 'votes'}`;

function FindingDetail({
  graph,
  item,
  selectedNode,
  onStep,
}: {
  graph: AtlasGraph;
  item: FindingItem;
  selectedNode: string | null;
  onStep: (id: string) => void;
}) {
  const evidence = item.access?.ownershipEvidence;
  return (
    <>
      <p className={`finding-status ${item.kind}`}>{statusText(item)}</p>
      <p className="qualified-name">
        {item.route.httpMethod} {item.route.pathTemplate}
      </p>
      {item.partialRoute && (
        <p className="notice is-warning">
          This route has gaps in its recorded coverage. Inspect its source for
          checks outside the recorded path.
        </p>
      )}
      {item.access ? (
        <section className="evidence-block">
          <h3>
            Cited access · {item.access.operation} {item.access.object.name}
          </h3>
          <dl>
            <dt>Owner in predicate</dt>
            <dd>{evidence!.inPredicate}</dd>
            <dt>Owner stamped on write</dt>
            <dd>{evidence!.stampedOnWrite}</dd>
            {evidence!.ownerFields.length > 0 && (
              <>
                <dt>Owner fields</dt>
                <dd>{evidence!.ownerFields.join(', ')}</dd>
              </>
            )}
            {item.access.paramFlows.length > 0 && (
              <>
                <dt>Request parameters</dt>
                <dd>
                  {item.access.paramFlows
                    .map((flow) => `${flow.entryParamId} → ${flow.field}`)
                    .join(', ')}
                </dd>
              </>
            )}
          </dl>
        </section>
      ) : (
        <p className="muted-note">
          These votes cite no data access, so no path can be placed on the
          graph.
        </p>
      )}
      <Excerpt snippet={item.evidence} label="Cited evidence" />
      <section className="evidence-block">
        <h3>Recorded path</h3>
        {item.occurrenceId ? (
          <ol className="finding-path">
            {item.path.map((id, index) => {
              const node = graph.nodes.get(id)!;
              return (
                <li key={id}>
                  <button
                    className={selectedNode === id ? 'is-current' : ''}
                    aria-current={selectedNode === id ? 'step' : undefined}
                    onClick={() => onStep(id)}
                  >
                    <span className="path-index">{index + 1}</span>
                    <span>
                      <strong>{node.name}</strong>
                      {node.range && (
                        <small>
                          {node.range.file}:{node.range.startLine}
                        </small>
                      )}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        ) : (
          <p className="muted-note">
            The cited access is not on a recorded call path in this graph.
          </p>
        )}
        <p className="muted-note">
          The path is static scan evidence from the entry to the cited access.
          It doesn't show that an exploit ran.
        </p>
      </section>
      <section className="evidence-block">
        <h3>Agent votes</h3>
        {!item.votes.length && (
          <p className="muted-note">
            No individual votes were saved for this finding.
          </p>
        )}
        <ul className="vote-list">
          {item.votes.map((vote) => (
            <li key={vote.id}>
              <span className={`vote-verdict ${vote.verdict}`}>
                {vote.verdict}
              </span>
              <span className="vote-role">{vote.role}</span>
              <p>{vote.reason}</p>
            </li>
          ))}
        </ul>
      </section>
      {item.check === 'idor' && (
        <section className="evidence-block">
          <h3>What to check next</h3>
          <p>
            Confirm whether the object is loaded or changed through a predicate
            on the authenticated caller, on every path to this access. If not,
            scope the query to the caller or add an ownership check before the
            access.
          </p>
        </section>
      )}
    </>
  );
}

/** The review summary and every finding and candidate, for the side rail. */
export function FindingsList({
  graph,
  index,
  scan,
  focusedId,
  onFocus,
}: {
  graph: AtlasGraph;
  index: FindingIndex;
  scan: ScanSummary;
  focusedId: string | null;
  onFocus: (item: FindingItem) => void;
}) {
  const [filter, setFilter] = useState<Filter>('all'),
    [query, setQuery] = useState('');
  const counts = {
    finding: index.items.filter((item) => item.kind === 'finding').length,
    candidate: index.items.filter((item) => item.kind === 'candidate').length,
  };
  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return index.items.filter(
      (item) =>
        (filter === 'all' || item.kind === filter) &&
        (!needle ||
          `${item.route.httpMethod} ${item.route.pathTemplate} ${item.route.handler.qualifiedName} ${item.access?.object.name || ''}`
            .toLowerCase()
            .includes(needle)),
    );
  }, [index.items, filter, query]);
  const { verdicts } = index;
  return (
    <section
      className="rail-section rail-list findings-rail"
      aria-label="Findings"
    >
      <p className="rail-note review-summary">
        Recorded votes for {index.reviewedRoutes} of{' '}
        {graph.document.routes.length} routes. {verdicts.present} present ·{' '}
        {verdicts.absent} absent · {verdicts.inconclusive} inconclusive.
      </p>
      {scan.findings.length > counts.finding && (
        <p className="notice">
          {scan.findings.length - counts.finding} saved finding(s) cite routes
          outside this graph.
        </p>
      )}
      {scan.status === 'partial' &&
        !scan.reviewing &&
        verdicts.inconclusive > 0 && (
          <p className="notice is-warning">
            {scan.progress} Inconclusive votes include failed or incomplete
            model calls, so a route without a finding is not cleared.
          </p>
        )}
      {index.inconclusiveReasons.length > 0 && (
        <details className="inconclusive-reasons">
          <summary>Why votes were inconclusive</summary>
          <ul>
            {index.inconclusiveReasons.map(([reason, count]) => (
              <li key={reason}>
                <b>{count}×</b> {reason}
              </li>
            ))}
          </ul>
        </details>
      )}
      {index.items.length > 0 && (
        <div className="findings-tools">
          <div
            className="segmented"
            role="radiogroup"
            aria-label="Filter findings"
          >
            {(
              [
                ['all', `All ${index.items.length}`],
                ['finding', `Findings ${counts.finding}`],
                ['candidate', `Candidates ${counts.candidate}`],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                role="radio"
                aria-checked={filter === value}
                onClick={() => setFilter(value)}
              >
                {label}
              </button>
            ))}
          </div>
          <label className="findings-search">
            <Search size={13} />
            <input
              aria-label="Filter findings by route, handler or object"
              placeholder="Route, handler or object"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
        </div>
      )}
      {!index.items.length ? (
        <p className="rail-note">
          {scan.reviewing
            ? 'No present votes yet.'
            : 'No findings or candidates are linked to a recorded route.'}
        </p>
      ) : !shown.length ? (
        <p className="rail-note">No findings match this filter.</p>
      ) : (
        <ul className="finding-list">
          {shown.map((item) => (
            <li key={item.id}>
              <button
                aria-current={focusedId === item.id ? 'true' : undefined}
                onClick={() => onFocus(item)}
              >
                <span className={`finding-kind ${item.kind}`}>
                  {item.kind === 'finding' ? 'Finding' : 'Candidate'}{' '}
                  {item.presentCount}/{item.threshold}
                </span>
                <strong>
                  <b>{item.route.httpMethod}</b> {item.route.pathTemplate}
                </strong>
                <small>
                  {checkName(item.check)}
                  {item.access &&
                    ` · ${item.access.operation} ${item.access.object.name}`}
                </small>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** One finding's explanation, evidence, votes and steppable path. */
export function FindingPanel({
  graph,
  item,
  selectedNode,
  onStep,
  onClose,
  returnFocus,
}: {
  graph: AtlasGraph;
  item: FindingItem;
  selectedNode: string | null;
  onStep: (id: string) => void;
  onClose: () => void;
  returnFocus: RefObject<HTMLElement | null>;
}) {
  const closeButton = useRef<HTMLButtonElement>(null),
    panel = useRef<HTMLElement>(null);
  useEffect(() => {
    const opener = returnFocus.current;
    closeButton.current?.focus({ preventScroll: true });
    return () => {
      if (opener?.isConnected) opener.focus({ preventScroll: true });
    };
  }, [returnFocus]);
  useEffect(() => {
    panel.current?.scrollTo(0, 0);
  }, [item.id]);
  return (
    <aside
      ref={panel}
      className="source-panel findings-panel"
      role="dialog"
      aria-modal="false"
      aria-labelledby="finding-title"
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          event.stopPropagation();
          onClose();
        }
      }}
    >
      <button
        ref={closeButton}
        className="icon-button source-close"
        onClick={onClose}
        aria-label="Close finding"
      >
        <X size={17} />
      </button>
      <div className="eyebrow">{checkName(item.check)}</div>
      <h2 id="finding-title">
        {item.route.handler.qualifiedName.split('.').at(-1)}
      </h2>
      <FindingDetail
        graph={graph}
        item={item}
        selectedNode={selectedNode}
        onStep={onStep}
      />
    </aside>
  );
}
