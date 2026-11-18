import {
  Box,
  ChartNoAxesGantt,
  ChevronDown,
  CircleDot,
  GitBranch,
  GitFork,
  Layers2,
  LogOut,
  Plus,
  Waypoints,
} from 'lucide-react';
import type { ReactNode } from 'react';
import type { ProjectView } from '../ProjectReport';
import { repositoryName } from '../api';
import { sample } from '../data';
import type { Project, User } from './api';
import { Brand } from './AccessPages';
import { go, projectAddress, sampleAddress } from './location';

const tabs = [
  { id: '3d', label: '3D Mode', icon: Box },
  { id: '2d', label: '2D Mode', icon: Waypoints },
  { id: 'routes', label: 'List of Routes', icon: ChartNoAxesGantt },
  { id: 'issues', label: 'Issues Found', icon: CircleDot },
] as const;
export function ProductFrame({
  user,
  projects,
  activeId,
  project,
  example,
  view,
  showTabs,
  onViewChange,
  onLogout,
  children,
}: {
  user: User | null;
  projects: Project[];
  activeId: string | null;
  project?: Project;
  example: boolean;
  view: ProjectView;
  showTabs: boolean;
  onViewChange: (view: ProjectView) => void;
  onLogout: () => void;
  children: ReactNode;
}) {
  const selected = example ? 'sample' : (activeId ?? 'new');
  return (
    <div className="product-frame">
      <header className="workspace-bar">
        <Brand onClick={() => go(user ? '?workspace=1' : '')} />
        <div className="bar-divider" />
        <div className="project-picker">
          <Layers2 size={14} />
          <select
            aria-label="Select project"
            value={selected}
            onChange={(e) => {
              const id = e.target.value;
              if (id === 'new') go(user ? '?new=1' : '?auth=register');
              else
                go(
                  id === 'sample'
                    ? sampleAddress(view)
                    : projectAddress(id, view),
                );
            }}
          >
            {selected === 'new' && <option value="new">Select project</option>}
            {activeId && !projects.some((p) => p.id === activeId) && (
              <option value={activeId}>
                {project
                  ? repositoryName(project.repositoryUrl)
                  : 'Selected project'}
              </option>
            )}
            {projects.length > 0 && (
              <optgroup label="Your projects">
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {repositoryName(p.repositoryUrl)}
                  </option>
                ))}
              </optgroup>
            )}
            <optgroup label="Public sample">
              <option value="sample">Aegra · sample</option>
            </optgroup>
          </select>
          <ChevronDown size={13} />
        </div>
        <div className="bar-actions">
          {user ? (
            <>
              <button className="add-project" onClick={() => go('?new=1')}>
                <Plus size={15} />
                New project
              </button>
              <span className="account-label" title={user.email}>
                {user.email}
              </span>
              <button
                className="sign-out"
                aria-label="Sign out"
                title="Sign out"
                onClick={onLogout}
              >
                <LogOut size={16} />
              </button>
            </>
          ) : (
            <button className="add-project" onClick={() => go('?auth=login')}>
              Sign in
            </button>
          )}
        </div>
      </header>
      {showTabs && (
        <div className="report-toolbar">
          <nav className="workspace-views" aria-label="Project views">
            {tabs.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => onViewChange(id)}
                aria-current={view === id ? 'page' : undefined}
              >
                <Icon size={15} strokeWidth={1.65} />
                <span>{label}</span>
              </button>
            ))}
          </nav>
          <div className="revision-stamp">
            <GitBranch size={13} />
            <span>
              {example
                ? sample.tag
                : project?.scan.revision || 'default branch'}
            </span>
            {(example || project?.scan.resolvedRevision) && (
              <code>
                {(example
                  ? sample.provenance.sourceRevision
                  : project!.scan.resolvedRevision
                ).slice(0, 7)}
              </code>
            )}
          </div>
        </div>
      )}
      {!showTabs && !example && (
        <div className="workspace-crumb">
          <GitFork size={14} /> Projects
        </div>
      )}
      <div className="workspace-module">{children}</div>
    </div>
  );
}
