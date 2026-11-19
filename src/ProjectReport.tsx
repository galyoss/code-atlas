import { Activity, lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { GitFork } from 'lucide-react';
import type { FileManifest } from './api';
import { PlanarGraph } from './components/PlanarGraph';
import { ReportLists } from './components/ReportLists';
import { indexFindings } from './graph/findings';
import type { AtlasGraph } from './graph/types';
import { sourceIdentity, type ScanSource } from './source';
import './report.css';

const CinematicGraph = lazy(() => import('./components/CinematicGraph'));

export type ProjectView = '3d' | '2d' | 'routes' | 'issues';
export interface TraceTarget {
  routeId: string;
  handlerId: string;
  findingId?: string;
}
interface ReportProps {
  graph: AtlasGraph;
  source: ScanSource;
  manifest?: FileManifest | null;
  view: ProjectView;
  onViewChange: (view: ProjectView) => void;
}

export function ProjectReport(props: ReportProps) {
  const { graph, source } = props;
  const id =
    source.kind === 'sample' ? 'sample' : (source.projectId ?? source.scan.id);
  return (
    <ReportContent key={`${id}/${graph.document.repo.revision}`} {...props} />
  );
}

function ReportContent({
  graph,
  source,
  manifest = null,
  view,
  onViewChange,
}: ReportProps) {
  const scan = source.kind === 'api' ? source.scan : null;
  const findings = useMemo(
    () =>
      scan
        ? indexFindings(
            graph,
            scan.findings,
            scan.votes,
            scan.agreementThreshold,
          )
        : null,
    [graph, scan],
  );
  const [trace, setTrace] = useState<TraceTarget | null>(null);
  const [visited2D, setVisited2D] = useState(false);
  // Preserve the camera and expanded branches after the first visit to the 2D graph.
  useEffect(() => {
    if (view === '2d') setVisited2D(true);
  }, [view]);
  const hasSymbols = graph.baseIds.length > 0;
  function inspect(target: TraceTarget) {
    setTrace(target);
    onViewChange('2d');
  }
  return (
    <div className="project-report" data-report-view={view}>
      {(view === '2d' || visited2D) && hasSymbols && (
        <Activity mode={view === '2d' ? 'visible' : 'hidden'}>
          <PlanarGraph
            graph={graph}
            source={source}
            manifest={manifest}
            findings={findings}
            trace={trace}
            onViewChange={onViewChange}
          />
        </Activity>
      )}
      {view === '3d' && hasSymbols && (
        <Suspense
          fallback={
            <div className="report-loading" role="status">
              Opening 3D graph…
            </div>
          }
        >
          <CinematicGraph graph={graph} onExit={() => onViewChange('2d')} />
        </Suspense>
      )}
      {(view === 'routes' || view === 'issues') && (
        <ReportLists
          key={view}
          graph={graph}
          source={source}
          findings={findings}
          view={view}
          onInspect={inspect}
        />
      )}
      {!hasSymbols && (view === '3d' || view === '2d') && (
        <section className="report-empty" aria-label="Empty graph">
          <GitFork size={24} strokeWidth={1.4} />
          <h2>No code nodes recorded</h2>
          <p>The scanner recorded no indexed symbols for this revision.</p>
          <a
            className="report-link"
            href={sourceIdentity(source).graphUrl}
            download={sourceIdentity(source).download}
          >
            Download graph JSON
          </a>
        </section>
      )}
    </div>
  );
}
