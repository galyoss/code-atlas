import { useCallback, useEffect, useRef, useState } from 'react';
import { type FileManifest, ApiError } from '../api';
import { loadSample, openDocument } from '../data';
import type { AtlasGraph } from '../graph/types';
import { ProjectReport, type ProjectView } from '../ProjectReport';
import {
  AuthPage,
  ConnectProject,
  JobProgress,
  Landing,
  Notice,
  Working,
} from './AccessPages';
import { ProductFrame } from './ProductFrame';
import {
  getFiles,
  getGraph,
  getProject,
  listProjects,
  retryProject,
  session,
  signOut,
  type Project,
  type User,
} from './api';
import {
  go,
  isSample,
  useMounted,
  projectAddress,
  sampleAddress,
  useAddress,
  viewOf,
} from './location';
import './product.css';

function ReportData({
  project,
  view,
  onViewChange,
}: {
  project?: Project;
  view: ProjectView;
  onViewChange: (v: ProjectView) => void;
}) {
  const [graph, setGraph] = useState<AtlasGraph | null>(null),
    [files, setFiles] = useState<FileManifest | null>(null);
  const [error, setError] = useState(''),
    [attempt, setAttempt] = useState(0);
  const id = project?.id,
    hasFiles = project?.scan.hasFiles;
  useEffect(() => {
    const c = new AbortController();
    setError('');
    const read = id
      ? getGraph(id, c.signal).then(openDocument)
      : loadSample(c.signal);
    read
      .then((g) => {
        if (!c.signal.aborted) setGraph(g);
      })
      .catch((err) => {
        if (!c.signal.aborted) setError(err.message);
      });
    if (id && hasFiles)
      getFiles(id, c.signal)
        .then((f) => {
          if (!c.signal.aborted) setFiles(f);
        })
        .catch(() => {
          /* The graph contains its referenced source files. */
        });
    return () => c.abort();
  }, [id, hasFiles, attempt]);
  if (error)
    return (
      <Working
        title="Couldn’t open the graph"
        action={
          <button
            className="product-secondary"
            onClick={() => setAttempt((a) => a + 1)}
          >
            Try again
          </button>
        }
      >
        {error}
      </Working>
    );
  if (!graph) return <Working title="Opening graph…" busy />;
  return (
    <ProjectReport
      graph={graph}
      source={
        project
          ? { kind: 'api', scan: project.scan, projectId: project.id }
          : { kind: 'sample' }
      }
      manifest={files}
      view={view}
      onViewChange={onViewChange}
    />
  );
}
function SelectedProject({
  id,
  view,
  onViewChange,
  onUpdate,
}: {
  id: string;
  view: ProjectView;
  onViewChange: (v: ProjectView) => void;
  onUpdate: (p: Project) => void;
}) {
  const [project, setProject] = useState<Project | null>(null),
    [readError, setReadError] = useState(''),
    [attempt, setAttempt] = useState(0);
  const [retryError, setRetryError] = useState(''),
    [retrying, setRetrying] = useState(false);
  const alive = useMounted();
  useEffect(() => {
    const c = new AbortController();
    let timer: number | undefined;
    async function poll() {
      try {
        const next = await getProject(id, c.signal);
        if (c.signal.aborted) return;
        setProject(next);
        onUpdate(next);
        setReadError('');
        if (next.scan.inProgress) timer = window.setTimeout(poll, 1600);
      } catch (err) {
        if (c.signal.aborted) return;
        setReadError((err as Error).message);
        if (!(err instanceof ApiError) || err.status >= 500)
          timer = window.setTimeout(poll, 4000);
      }
    }
    void poll();
    return () => {
      c.abort();
      window.clearTimeout(timer);
    };
  }, [id, onUpdate, attempt]);
  async function retry() {
    setRetrying(true);
    setRetryError('');
    try {
      const p = await retryProject(id);
      if (alive.current) {
        setProject(p);
        onUpdate(p);
        setAttempt((a) => a + 1);
      }
    } catch (err) {
      if (alive.current) setRetryError((err as Error).message);
    } finally {
      if (alive.current) setRetrying(false);
    }
  }
  if (readError)
    return (
      <Working
        title="Project unavailable"
        action={
          <button
            className="product-secondary"
            onClick={() => setAttempt((a) => a + 1)}
          >
            Try again
          </button>
        }
      >
        {readError}
      </Working>
    );
  if (!project) return <Working title="Opening project…" busy />;
  if (!project.scan.hasGraph)
    return (
      <JobProgress
        project={project}
        busy={retrying}
        onRetry={retry}
        error={retryError}
      />
    );
  return (
    <ReportData
      key={project.scan.id}
      project={project}
      view={view}
      onViewChange={onViewChange}
    />
  );
}
function Workspace({
  user,
  onLogout,
}: {
  user: User | null;
  onLogout: () => void;
}) {
  const params = useAddress(),
    id = params.get('project'),
    example = isSample(params),
    view = viewOf(params);
  const [projects, setProjects] = useState<Project[] | null>(null),
    [error, setError] = useState(''),
    [attempt, setAttempt] = useState(0);
  const useDefault =
    !id && !example && !params.has('new') && !params.has('scan');
  // Merge list reads with project updates that finished while the list was loading.
  const locallyRead = useRef(new Map<string, Project>());
  const updateProject = useCallback((p: Project) => {
    locallyRead.current.set(p.id, p);
    setProjects((prev) => [p, ...(prev ?? []).filter((x) => x.id !== p.id)]);
  }, []);
  useEffect(() => {
    if (!user) return;
    const c = new AbortController();
    setError('');
    listProjects(c.signal)
      .then((list) => {
        if (!c.signal.aborted) {
          const byId = new Map(list.map((p) => [p.id, p]));
          for (const [key, project] of locallyRead.current)
            byId.set(key, project);
          setProjects([...byId.values()]);
        }
      })
      .catch((err) => {
        if (!c.signal.aborted) setError(err.message);
      });
    return () => c.abort();
  }, [user?.id, attempt]);
  useEffect(() => {
    if (user && useDefault && projects)
      go(
        projects.length ? projectAddress(projects[0].id, '3d') : '?new=1',
        true,
      );
  }, [user, useDefault, projects]);
  const changeView = (v: ProjectView) =>
    go(example ? sampleAddress(v) : projectAddress(id!, v));
  const project = projects?.find((p) => p.id === id);
  return (
    <ProductFrame
      user={user}
      projects={projects ?? []}
      activeId={id}
      project={project}
      example={example}
      view={view}
      showTabs={!!id || example}
      onViewChange={changeView}
      onLogout={onLogout}
    >
      {error && (
        <div className="list-notice">
          <Notice>
            {error}{' '}
            <button onClick={() => setAttempt((a) => a + 1)}>
              Reload projects
            </button>
          </Notice>
        </div>
      )}
      {example ? (
        <ReportData key="sample" view={view} onViewChange={changeView} />
      ) : id ? (
        <SelectedProject
          key={id}
          id={id}
          view={view}
          onViewChange={changeView}
          onUpdate={updateProject}
        />
      ) : params.has('scan') ? (
        <Working
          title="This link belongs to the standalone scan service"
          action={
            <button className="product-secondary" onClick={() => go('?new=1')}>
              Open a repository project
            </button>
          }
        >
          Workspace projects have their own saved reports and project links.
        </Working>
      ) : params.has('new') || error ? (
        <ConnectProject
          onCreated={(p, stillHere) => {
            updateProject(p);
            if (stillHere) go(projectAddress(p.id, '3d'));
          }}
        />
      ) : (
        <Working title="Opening workspace…" busy />
      )}
    </ProductFrame>
  );
}

export default function WorkspaceApp() {
  const params = useAddress();
  const [user, setUser] = useState<User | null>(null),
    [pending, setPending] = useState(true),
    [error, setError] = useState('');
  const initialRequest = useRef<AbortController | null>(null);
  useEffect(() => {
    let active = true;
    const sync = () => {
      initialRequest.current?.abort();
      const c = new AbortController();
      initialRequest.current = c;
      session(c.signal)
        .then((s) => {
          if (active && !c.signal.aborted) {
            setUser(s.user);
            setError('');
          }
        })
        .catch((err) => {
          if (active && !c.signal.aborted) setError(err.message);
        })
        .finally(() => {
          if (active && !c.signal.aborted) setPending(false);
        });
    };
    const expired = () => {
      initialRequest.current?.abort();
      setUser(null);
      setPending(false);
    };
    sync();
    window.addEventListener('atlas-session-ended', expired);
    window.addEventListener('focus', sync);
    return () => {
      active = false;
      initialRequest.current?.abort();
      window.removeEventListener('atlas-session-ended', expired);
      window.removeEventListener('focus', sync);
    };
  }, []);
  async function logout() {
    try {
      await signOut();
    } catch (err) {
      if (!(err instanceof ApiError && err.status === 401)) {
        setError((err as Error).message);
        return;
      }
    }
    initialRequest.current?.abort();
    setUser(null);
    setPending(false);
    setError('');
    go('', true);
  }
  const example = isSample(params),
    protectedLink = ['project', 'new', 'workspace', 'scan'].some((k) =>
      params.has(k),
    );
  const mode = params.get('auth') === 'register' ? 'register' : 'login';
  if (example || user)
    return (
      <>
        {error && user && <Notice>{error}</Notice>}
        <Workspace key={user?.id ?? 'guest'} user={user} onLogout={logout} />
      </>
    );
  if (pending && protectedLink)
    return <Working title="Opening workspace…" busy />;
  if (params.has('auth') || protectedLink)
    return (
      <AuthPage
        key={mode}
        mode={mode}
        serviceError={error}
        onMode={() => {
          const next = new URLSearchParams(params);
          next.set('auth', mode === 'login' ? 'register' : 'login');
          go('?' + next);
        }}
        onUser={(next) => {
          initialRequest.current?.abort();
          setUser(next);
          setPending(false);
          setError('');
          if (protectedLink) {
            const dest = new URLSearchParams(params);
            dest.delete('auth');
            go('?' + dest, true);
          } else go('?workspace=1', true);
        }}
      />
    );
  return <Landing />;
}
