import { useRef, useState, type FormEvent, type ReactNode } from 'react';
import {
  ArrowDownRight,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Box,
  Check,
  CircleAlert,
  GitBranch,
  GitFork,
  Github,
  LoaderCircle,
  LockKeyhole,
  Orbit,
} from 'lucide-react';
import { sample } from '../data';
import cover from './aegra-cover.webp';
import { authenticate, newProject, type Project, type User } from './api';
import { go, sampleAddress, useMounted } from './location';

export function Brand({ onClick }: { onClick: () => void }) {
  return (
    <button
      className="product-brand"
      onClick={onClick}
      aria-label="CodeAtlas home"
    >
      <Orbit size={24} strokeWidth={1.55} />
      CodeAtlas
    </button>
  );
}
export function Notice({ children }: { children: ReactNode }) {
  return (
    <div className="product-notice" role="alert">
      <CircleAlert size={16} />
      <span>{children}</span>
    </div>
  );
}
export function Cover() {
  return (
    <figure className="atlas-plate">
      <img
        src={cover}
        alt="File clusters and recorded connections in the Aegra code graph"
        width="1500"
        height="1010"
      />
      <figcaption>
        <span>
          <span className="plate-dot" /> aegra / aegra
        </span>
        <span>
          {sample.provenance.counts.routes} routes ·{' '}
          {sample.provenance.counts.symbols} symbols
        </span>
      </figcaption>
    </figure>
  );
}
export function Landing() {
  return (
    <main className="atlas-frontdoor">
      <header className="front-nav">
        <Brand onClick={() => go('')} />
        <button className="quiet-link" onClick={() => go('?auth=login')}>
          Sign in <ArrowUpRight size={15} />
        </button>
      </header>
      <div className="landing-hero">
        <section className="landing-copy">
          <span className="section-label">
            <GitFork size={15} /> Repository explorer
          </span>
          <h1>
            Follow the code<span>.</span>
          </h1>
          <p>
            Turn a public repository into an interactive map. Follow a request
            from its entry point to the code that reads or writes data.
          </p>
          <div className="landing-actions">
            <button
              className="product-primary"
              onClick={() => go('?auth=register')}
            >
              Create workspace <ArrowRight size={16} />
            </button>
            <a className="quiet-link" href={sampleAddress()}>
              Explore Aegra <ArrowUpRight size={15} />
            </a>
          </div>
        </section>
        <a
          className="cover-link"
          href={sampleAddress()}
          aria-label="Explore the Aegra sample in 3D"
        >
          <Cover />
        </a>
      </div>
      <footer className="landing-footer">
        <span>
          <Box size={15} /> Interactive code graphs
        </span>
        <span>
          Public GitHub repositories <Github size={15} />
        </span>
      </footer>
    </main>
  );
}
export function AuthPage({
  mode,
  onMode,
  onUser,
  serviceError,
}: {
  mode: 'register' | 'login';
  onMode: () => void;
  onUser: (user: User) => void;
  serviceError?: string;
}) {
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const form = useRef<HTMLFormElement>(null);
  const register = mode === 'register';
  const mounted = useMounted();
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    const fields = new FormData(form.current!);
    setBusy(true);
    setError('');
    try {
      const result = await authenticate(
        mode,
        String(fields.get('email')),
        String(fields.get('password')),
      );
      if (mounted.current) onUser(result.user);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="atlas-frontdoor">
      <header className="front-nav">
        <Brand onClick={() => go('')} />
        <button className="quiet-link" onClick={() => go('')}>
          <ArrowLeft size={15} /> Home
        </button>
      </header>
      <div className="auth-layout">
        <section className="auth-sheet">
          <span className="section-label">
            <LockKeyhole size={14} /> Atlas workspace
          </span>
          <h1>{register ? 'Create your account' : 'Welcome back'}</h1>
          <p>
            {register
              ? 'Save projects and return to the code you’re exploring.'
              : 'Sign in to open your repository projects.'}
          </p>
          <form ref={form} onSubmit={submit}>
            <label>
              Email
              <input
                name="email"
                type="email"
                autoComplete="email"
                required
                maxLength={254}
                placeholder="you@example.com"
              />
            </label>
            <label>
              Password
              <input
                name="password"
                type="password"
                autoComplete={register ? 'new-password' : 'current-password'}
                required
                minLength={register ? 10 : 1}
                maxLength={128}
                aria-describedby={register ? 'password-note' : undefined}
              />
            </label>
            {register && (
              <small id="password-note">Use at least 10 characters.</small>
            )}
            {(error || serviceError) && (
              <Notice>{error || serviceError}</Notice>
            )}
            <button className="product-primary" disabled={busy}>
              {register ? 'Create account' : 'Sign in'}{' '}
              {busy ? (
                <LoaderCircle className="product-spin" size={16} />
              ) : (
                <ArrowRight size={16} />
              )}
            </button>
          </form>
          <p className="auth-switch">
            {register ? 'Already have an account?' : 'New to Atlas?'}{' '}
            <button onClick={onMode}>
              {register ? 'Sign in' : 'Create account'}
            </button>
          </p>
        </section>
        <div className="auth-art">
          <Cover />
        </div>
      </div>
    </main>
  );
}
export function ConnectProject({
  onCreated,
}: {
  onCreated: (p: Project, stillHere: boolean) => void;
}) {
  const mounted = useMounted();
  const [url, setUrl] = useState(''),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setError('');
    setBusy(true);
    try {
      const created = await newProject(url.trim());
      onCreated(created, mounted.current);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="connect-screen">
      <div className="connect-panel">
        <span className="section-label">
          <GitBranch size={15} /> New project
        </span>
        <h1>Connect a repository</h1>
        <p>
          Paste a public GitHub URL. Atlas will scan its default branch and save
          the graph in your workspace.
        </p>
        <form onSubmit={submit}>
          <label htmlFor="repo-url">Repository URL</label>
          <div className="repository-input">
            <Github size={18} />
            <input
              id="repo-url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              required
              autoComplete="off"
              spellCheck={false}
              placeholder="https://github.com/owner/repository"
            />
          </div>
          <small>Route detection supports FastAPI, Express and Rails.</small>
          {error && <Notice>{error}</Notice>}
          <button disabled={busy || !url.trim()} className="product-primary">
            {busy ? 'Creating project…' : 'Create project & scan'}{' '}
            <ArrowRight size={15} />
          </button>
        </form>
        <a href={sampleAddress()} className="sample-inline">
          <ArrowDownRight size={15} /> Explore the Aegra sample
        </a>
      </div>
    </section>
  );
}
export function Working({
  title,
  children,
  action,
  busy = false,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  busy?: boolean;
}) {
  return (
    <section className="workspace-state" aria-live="polite">
      {busy ? (
        <LoaderCircle className="product-spin" size={24} />
      ) : (
        <GitBranch size={24} />
      )}
      <h2>{title}</h2>
      {children && <p>{children}</p>}
      {action}
    </section>
  );
}
export function JobProgress({
  project,
  onRetry,
  error,
  busy,
}: {
  project: Project;
  onRetry: () => void;
  error: string;
  busy: boolean;
}) {
  const scan = project.scan,
    failed = scan.status === 'failed',
    running = scan.status === 'running';
  return (
    <div className="scan-sheet" aria-live="polite">
      <span className="section-label">
        <GitBranch size={14} /> Repository scan
      </span>
      <h1>
        {failed
          ? 'Scan interrupted'
          : running
            ? 'Building your graph'
            : 'Scan queued'}
      </h1>
      <p>{failed ? scan.error || scan.progress : scan.progress}</p>
      {!failed && (
        <ol className="build-steps">
          <li>
            <Check size={15} /> Project created
          </li>
          <li className={running ? 'active' : ''}>
            {running ? (
              <LoaderCircle className="product-spin" size={15} />
            ) : (
              <span />
            )}{' '}
            Build code graph
          </li>
          <li>
            <span /> Open saved graph
          </li>
        </ol>
      )}
      {error && <Notice>{error}</Notice>}
      {failed && (
        <button className="product-primary" disabled={busy} onClick={onRetry}>
          Retry scan <ArrowRight size={15} />
        </button>
      )}
      {!failed && <small>You can switch projects while this scan runs.</small>}
    </div>
  );
}
