import { useEffect, useRef, type RefObject } from 'react';
import { X } from 'lucide-react';
import { sample } from '../data';
import { sourceIdentity, type ScanSource } from '../source';
import { callNodeId } from '../graph/adapter';
import {
  accessSummary,
  dataEffect,
  effectGlyph,
  persistenceEffect,
  effectLabel,
} from '../graph/semantics';
import type {
  AtlasGraph,
  AuthStep,
  DataAccess,
  GraphNode,
  Route,
  Snippet,
  SourceRange,
} from '../graph/types';

const location = (range: SourceRange) =>
  `${range.file}:${range.startLine}${range.endLine === range.startLine ? '' : `–${range.endLine}`}`;
export function Excerpt({
  snippet,
  label = 'Source excerpt',
}: {
  snippet?: Snippet;
  label?: string;
}) {
  return snippet ? (
    <section className="evidence-block">
      <h3>{label}</h3>
      <p className="source-location">{location(snippet.range)}</p>
      <pre>
        <code>{snippet.text}</code>
      </pre>
      {snippet.truncated && (
        <p className="muted-note">Excerpt truncated in the scan document.</p>
      )}
    </section>
  ) : null;
}
function AuthEvidence({ step }: { step: AuthStep }) {
  return (
    <section className="evidence-block">
      <h3>
        {step.kind === 'authorization'
          ? 'Authorization check'
          : 'Authentication check'}
      </h3>
      <p>{step.qualifiedName}</p>
      <p className="source-location">{location(step.range)}</p>
      <dl>
        <dt>Applies</dt>
        <dd>{step.applicability}</dd>
        <dt>On failure</dt>
        <dd>{step.onFailure}</dd>
        <dt>Object bound to caller</dt>
        <dd>{step.bindsObjectToCaller}</dd>
      </dl>
      {step.snippet && <Excerpt snippet={step.snippet} label="Check excerpt" />}
    </section>
  );
}
function AccessEvidence({
  access,
  route,
  occurrence,
}: {
  access: DataAccess;
  route: Route;
  occurrence: GraphNode;
}) {
  return (
    <section className="evidence-block">
      <h3>
        {access.operation} {access.object.name}
      </h3>
      {
        <p className="source-location">
          {route.httpMethod} {route.pathTemplate} · {access.callId}
        </p>
      }
      <p className="source-location">{location(occurrence.range!)}</p>
      <dl>
        <dt>Access record</dt>
        <dd>{access.id}</dd>
        <dt>Call resolution</dt>
        <dd>{occurrence.call?.resolution}</dd>
        {occurrence.evidence?.authStepId && (
          <>
            <dt>Auth step</dt>
            <dd>{occurrence.evidence.authStepId}</dd>
          </>
        )}
        <dt>Persistence API</dt>
        <dd>{access.persistenceApi}</dd>
        <dt>Store</dt>
        <dd>{access.object.store || 'Not recorded'}</dd>
        <dt>Owner in predicate</dt>
        <dd>{access.ownershipEvidence.inPredicate}</dd>
        <dt>Owner stamped on write</dt>
        <dd>{access.ownershipEvidence.stampedOnWrite}</dd>
        {access.ownershipEvidence.ownerFields.length > 0 && (
          <>
            <dt>Owner fields</dt>
            <dd>{access.ownershipEvidence.ownerFields.join(', ')}</dd>
          </>
        )}
      </dl>
      <Excerpt snippet={access.snippet} label="Data access excerpt" />
      {access.paramFlows.length > 0 && (
        <details>
          <summary>Request parameter flows</summary>
          {access.paramFlows.map((flow, index) => (
            <p key={index}>
              {flow.entryParamId} → {flow.field}{' '}
              <span className="muted-note">({flow.confidence})</span>
            </p>
          ))}
        </details>
      )}
      {access.writtenFields.length > 0 && (
        <details>
          <summary>Written fields</summary>
          {access.writtenFields.map((field) => (
            <p key={field.field}>
              {field.field} <span className="muted-note">← {field.source}</span>
            </p>
          ))}
        </details>
      )}
    </section>
  );
}
function ScopeEvidence({
  graph,
  source,
}: {
  graph: AtlasGraph;
  source: ScanSource;
}) {
  const { document } = graph;
  const identity = sourceIdentity(source);
  const scan = source.kind === 'api' ? source.scan : null;
  const hasReview =
    !!scan &&
    (scan.reviewing || scan.votes.length > 0 || scan.findings.length > 0);
  return (
    <>
      {document.note && <p>{document.note}</p>}
      <p>
        {document.routes.length} {document.frameworks.join(', ')} route slices
        and {document.symbolIndex.length} indexed symbols are included. A static
        scan does not establish which endpoints are deployed. Coverage is
        route-oriented, not a complete repository call graph.{' '}
        {hasReview && scan
          ? scan.reviewing
            ? 'Review agents are still voting on routes.'
            : `Review agents voted on ${new Set(scan.votes.map((vote) => vote.routeId)).size} of ${document.routes.length} routes.`
          : 'No security review results were recorded for this revision.'}
      </p>
      <dl>
        <dt>Repository</dt>
        <dd>
          {scan ? scan.repositoryUrl : identity.name} · {identity.tag}
        </dd>
        <dt>Revision</dt>
        <dd>{document.repo.revision}</dd>
        <dt>Frameworks</dt>
        <dd>{document.frameworks.join(', ')}</dd>
        <dt>Schema</dt>
        <dd>{document.schemaVersion}</dd>
        <dt>Generated (UTC)</dt>
        <dd>{document.generatedAt}</dd>
        {scan ? (
          <>
            <dt>Scan</dt>
            <dd>{scan.id}</dd>
            {hasReview && (
              <>
                <dt>Review model</dt>
                <dd>{scan.model}</dd>
                <dt>Agents / agreement</dt>
                <dd>
                  {scan.agentCount} / {scan.agreementThreshold}
                </dd>
              </>
            )}
            <dt>Status</dt>
            <dd>{scan.progress}</dd>
          </>
        ) : (
          <>
            <dt>Scanner revision</dt>
            <dd>{sample.provenance.scannerRevision}</dd>
            <dt>Joern / Java</dt>
            <dd>
              {sample.provenance.joernVersion} / {sample.provenance.javaVersion}
            </dd>
            <dt>Document SHA-256</dt>
            <dd>{sample.provenance.sha256}</dd>
          </>
        )}
      </dl>
      <p>
        <a href={identity.graphUrl} download={identity.download}>
          Download the unchanged scan document
        </a>
      </p>
      <details>
        <summary>Coverage for all {document.routes.length} routes</summary>
        {document.routes.map((route) => (
          <section className="evidence-block" key={route.id}>
            <h3>
              {route.httpMethod} {route.pathTemplate}
            </h3>
            <dl>
              <dt>Auth chain</dt>
              <dd>{route.budget.coverage.authChain}</dd>
              <dt>Call graph</dt>
              <dd>{route.budget.coverage.callGraph}</dd>
              <dt>Data flow</dt>
              <dd>{route.budget.coverage.dataFlow}</dd>
            </dl>
          </section>
        ))}
      </details>
      <section className="evidence-block">
        <h3>Known gaps</h3>
        {document.unresolvedGaps.map((gap) => (
          <p key={gap.id}>
            <strong>
              {gap.kind.replaceAll('_', ' ')} · {gap.support}
            </strong>
            <br />
            {gap.detail}
          </p>
        ))}
      </section>
      <p>
        Graph positions group relationships; they do not establish execution
        order. Authentication context and data summaries are distinct from
        recorded calls.
      </p>
    </>
  );
}
interface Props {
  graph: AtlasGraph;
  source: ScanSource;
  node: GraphNode;
  mode: 'source' | 'scope';
  routeId?: string;
  onClose: () => void;
  returnFocus: RefObject<HTMLButtonElement | null>;
}
export function SourcePanel({
  graph,
  source,
  node,
  mode,
  routeId,
  onClose,
  returnFocus,
}: Props) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    const opener = returnFocus.current;
    closeButton.current?.focus({ preventScroll: true });
    return () => {
      if (opener?.isConnected) opener.focus({ preventScroll: true });
    };
  }, [returnFocus]);
  useEffect(() => {
    panel.current?.scrollTo(0, 0);
  }, [node.id, mode]);
  const summary = accessSummary(node),
    effect = dataEffect(node);
  const callEffect = persistenceEffect(node.call?.touchesPersistence);
  const checks =
    node.route?.authChain.filter(
      (step) =>
        step.mechanism === 'inline' && step.symbolId === node.symbol?.id,
    ) || [];
  const omissions =
    node.route?.budget.omitted.filter(
      (item) => !node.call || item.callId === node.call.id,
    ) || [];
  return (
    <aside
      ref={panel}
      id="source-panel"
      className="source-panel"
      role="dialog"
      aria-modal="false"
      aria-labelledby="source-title"
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
        aria-label="Close source panel"
      >
        <X size={17} />
      </button>
      <div className="eyebrow">
        {mode === 'scope' ? 'Graph scope' : 'Source evidence'}
      </div>
      <h2 id="source-title">
        {mode === 'scope'
          ? `${sourceIdentity(source).name} · ${source.kind === 'sample' ? 'sample scan' : 'scan'}`
          : node.name}
      </h2>
      {mode === 'scope' ? (
        <ScopeEvidence graph={graph} source={source} />
      ) : (
        <>
          <p className="qualified-name">
            {node.call?.qualifiedName ||
              node.symbol?.qualifiedName ||
              node.name}
          </p>
          {node.range && (
            <p className="source-location">{location(node.range)}</p>
          )}
          {!!summary.total && (
            <section className="data-summary">
              <h3>
                {effect && (
                  <span className={`effect-badge ${effect}`}>
                    {effectGlyph(effect)}
                  </span>
                )}
                {node.canonical
                  ? 'Data access in this function body'
                  : 'Named object access'}
              </h3>
              <p>
                {summary.read} read · {summary.write} write
                {summary.unknown ? ` · ${summary.unknown} unknown` : ''}{' '}
                {node.canonical ? 'route-scoped records' : 'records'}
              </p>
              {node.canonical && (
                <p>
                  Badges summarize the recorded accesses directly owned by this
                  function. Repeated route slices remain separate; these are not
                  runtime counts or unique code sites.
                </p>
              )}
            </section>
          )}
          {node.symbol && (
            <section className="evidence-block">
              <h3>Declaration</h3>
              <p className="source-location">{location(node.symbol.range)}</p>
              <pre>
                <code>{node.symbol.signature}</code>
              </pre>
            </section>
          )}
          {node.call && (
            <>
              <dl>
                <dt>Route</dt>
                <dd>
                  {node.route?.httpMethod} {node.route?.pathTemplate}
                </dd>
                {node.evidence?.authStepId && (
                  <>
                    <dt>Auth step</dt>
                    <dd>{node.evidence.authStepId}</dd>
                  </>
                )}
                <dt>Call occurrence</dt>
                <dd>{node.call.id}</dd>
                <dt>Resolution</dt>
                <dd>{node.call.resolution}</dd>
                <dt>Persistence effect</dt>
                <dd>
                  {callEffect
                    ? effectLabel(callEffect)
                    : node.call.touchesPersistence === 'none'
                      ? 'None recorded'
                      : 'Unknown'}
                </dd>
                <dt>Recorded expansion</dt>
                <dd>{node.call.expanded}</dd>
                <dt>Recorded order</dt>
                <dd>{node.call.order}</dd>
              </dl>
              {callEffect && (
                <p className="muted-note">
                  Persistence effect is recorded on this call. It may describe a
                  nested operation or transaction; named object accesses are
                  listed separately.
                </p>
              )}
              {node.call.argumentsExcerpt && (
                <section className="evidence-block">
                  <h3>Invocation</h3>
                  <pre>
                    <code>{node.call.argumentsExcerpt}</code>
                  </pre>
                </section>
              )}
              <Excerpt snippet={node.call.snippet} />
              {node.call.resolution === 'ambiguous' && (
                <p className="coverage-note">
                  This invocation is recorded, but its runtime target is
                  unresolved. No target is inferred from the invocation name.
                </p>
              )}
              {node.call.resolution === 'external' && (
                <p className="coverage-note">
                  External call. Its implementation is outside this repository
                  slice.
                </p>
              )}
              {node.call.expanded === 'partial' && (
                <p className="coverage-note">
                  Partial expansion: these {node.children.length} recorded
                  children are not the complete function body.
                </p>
              )}
              {node.call.expanded === 'no' &&
                node.call.resolution === 'resolved' && (
                  <p className="coverage-note">
                    This call was not expanded in the scan document.
                  </p>
                )}
            </>
          )}
          {node.groupedRoutes?.map((route) => (
            <section key={route.id}>
              <h3>
                {route.httpMethod} {route.pathTemplate}
              </h3>
              <Excerpt
                snippet={route.registration.snippet}
                label="Route registration"
              />
            </section>
          ))}
          {node.canonical && (
            <section className="evidence-block">
              <h3>Recorded call relationships</h3>
              <p>
                {routeId
                  ? 'Directed static relationships in the selected route.'
                  : 'Directed static relationships, aggregated across route slices.'}{' '}
                Counts reflect recorded occurrences.
              </p>
              {graph.edges
                .filter(
                  (edge) =>
                    edge.aggregated &&
                    (edge.from === node.id || edge.to === node.id),
                )
                .map((edge) => {
                  const evidence = routeId
                    ? edge.evidence.filter((ref) => ref.routeId === routeId)
                    : edge.evidence;
                  if (!evidence.length) return null;
                  const outgoing = edge.from === node.id;
                  const other = graph.nodes.get(
                    outgoing ? edge.to : edge.from,
                  )!;
                  return (
                    <details key={edge.id}>
                      <summary>
                        {outgoing ? 'Calls' : 'Called by'} {other.name} ·{' '}
                        {evidence.length} records
                      </summary>
                      <p className="source-location">
                        {other.symbol?.qualifiedName}
                      </p>
                      {evidence.map((ref) => {
                        const occurrence = graph.nodes.get(
                          callNodeId(ref.routeId, ref.callId, ref.authStepId),
                        )!;
                        return (
                          <section
                            className="evidence-block"
                            key={occurrence.id}
                          >
                            <p>
                              {occurrence.route?.httpMethod}{' '}
                              {occurrence.route?.pathTemplate}
                            </p>
                            <p className="source-location">
                              {ref.callId}
                              {ref.authStepId
                                ? ` · auth: ${ref.authStepId}`
                                : ''}
                            </p>
                            <p className="source-location">
                              {location(occurrence.range!)}
                            </p>
                            {occurrence.call?.argumentsExcerpt && (
                              <pre>
                                <code>{occurrence.call.argumentsExcerpt}</code>
                              </pre>
                            )}
                            <Excerpt snippet={occurrence.call?.snippet} />
                          </section>
                        );
                      })}
                    </details>
                  );
                })}
            </section>
          )}
          {checks.map((step) => (
            <AuthEvidence key={step.id} step={step} />
          ))}
          {node.authSteps.length > 0 && (
            <>
              <p className="coverage-note">
                Authentication context for {node.authSteps.length} route{' '}
                {node.authSteps.length === 1 ? 'slice' : 'slices'}. Handler
                detail exposes each route's auth context and its recorded calls.
              </p>
              {node.authSteps.map(({ route, step }) => (
                <section
                  className="evidence-block"
                  key={`${route.id}:${step.id}`}
                >
                  <h3>
                    {route.httpMethod} {route.pathTemplate}
                  </h3>
                  <AuthEvidence step={step} />
                </section>
              ))}
            </>
          )}
          {node.accesses.map(({ route, access, occurrenceId }) => (
            <AccessEvidence
              key={`${route.id}:${access.id}`}
              route={route}
              access={access}
              occurrence={graph.nodes.get(occurrenceId)!}
            />
          ))}
          {!node.call?.snippet &&
            !node.call?.argumentsExcerpt &&
            !node.authSteps.length &&
            !node.accesses.length &&
            node.kind !== 'route' && (
              <p>No source excerpt is attached to this item.</p>
            )}
          {node.route && (
            <section className="evidence-block">
              <h3>Route coverage</h3>
              <p>
                {node.route.httpMethod} {node.route.pathTemplate}
              </p>
              <dl>
                <dt>Auth chain</dt>
                <dd>{node.route.budget.coverage.authChain}</dd>
                <dt>Call graph</dt>
                <dd>{node.route.budget.coverage.callGraph}</dd>
                <dt>Data flow</dt>
                <dd>{node.route.budget.coverage.dataFlow}</dd>
              </dl>
              {omissions.length > 0 && (
                <details>
                  <summary>
                    {omissions.length} recorded{' '}
                    {omissions.length === 1 ? 'omission' : 'omissions'}
                  </summary>
                  {omissions.map((item) => (
                    <p key={item.id}>
                      <strong>{item.reason.replaceAll('_', ' ')}</strong>
                      <br />
                      {item.detail}
                    </p>
                  ))}
                </details>
              )}
            </section>
          )}
          <p className="panel-footnote">
            Real Joern scan · partial static analysis · no agent security
            review.
          </p>
        </>
      )}
    </aside>
  );
}
