import { useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import { Search, X } from 'lucide-react';
import { handlerName, matchingRoutes, routeChoice, type RouteGroup } from '../graph/catalog';

interface Props {
  groups: RouteGroup[];
  file?: string;
  selected: string | null;
  onChoose: (id: string) => void;
  onClose: () => void;
  returnFocus: RefObject<HTMLButtonElement | null>;
}
export function RouteDirectory({ groups, file, selected, onChoose, onClose, returnFocus }: Props) {
  const [query, setQuery] = useState('');
  const [scope, setScope] = useState(file);
  const input = useRef<HTMLInputElement>(null);
  const matches = useMemo(
    () => matchingRoutes(scope ? groups.filter((g) => g.file === scope) : groups, query),
    [groups, scope, query],
  );
  const count = matches.reduce((sum, group) => sum + group.routes.length, 0);
  useEffect(() => {
    const opener = returnFocus.current;
    input.current?.focus({ preventScroll: true });
    return () => {
      if (opener?.isConnected) opener.focus({ preventScroll: true });
    };
  }, [returnFocus]);
  return (
    <aside
      className="route-directory"
      role="dialog"
      aria-modal="false"
      aria-labelledby="directory-title"
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          event.stopPropagation();
          onClose();
        }
      }}
    >
      <div className="directory-header">
        <div>
          <p className="eyebrow">Route directory</p>
          <h2 id="directory-title">Explore a handler</h2>
        </div>
        <button className="icon-button" onClick={onClose} aria-label="Close route directory">
          <X size={17} />
        </button>
      </div>
      <label className="route-search">
        <Search size={16} />
        <input
          ref={input}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search name, path, method…"
          aria-label="Search routes"
        />
      </label>
      <div className="directory-scope">
        <span>
          {count} {count === 1 ? 'route' : 'routes'}
          {scope ? ` in ${scope.split('/').at(-1)}` : ' across the scan'}
        </span>
        {scope && <button onClick={() => setScope(undefined)}>All files</button>}
      </div>
      <div className="directory-results">
        {matches.map((group) => (
          <section key={group.file} className="directory-group">
            <h3 title={group.file}>{group.file}</h3>
            {group.routes.map((route) => (
              <button
                key={route.id}
                className="directory-route"
                aria-pressed={selected === routeChoice(route).id}
                onClick={() => onChoose(routeChoice(route).id)}
              >
                <strong>{handlerName(route)}</strong>
                <span>
                  <b>{route.httpMethod}</b> {route.pathTemplate}
                </span>
              </button>
            ))}
          </section>
        ))}
        {!count && <p className="directory-empty">No recorded routes match this search.</p>}
      </div>
    </aside>
  );
}
