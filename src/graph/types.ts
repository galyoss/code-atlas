/** The consumed subset of schema v1.0.0. The source documents remain authoritative. */
export interface SourceRange {
  file: string;
  startLine: number;
  endLine: number;
}
export interface Snippet {
  text: string;
  truncated: boolean;
  range: SourceRange;
}
export interface SymbolDefinition {
  id: string;
  name: string;
  qualifiedName: string;
  signature: string;
  range: SourceRange;
}
export interface Call {
  id: string;
  order: number;
  depth: number;
  calleeName: string;
  qualifiedName: string;
  resolution: string;
  touchesPersistence: string;
  expanded: string;
  callSite: SourceRange;
  children: Call[];
  symbolId?: string;
  argumentsExcerpt?: string;
  snippet?: Snippet;
  candidates?: { symbolId?: string; qualifiedName?: string }[];
}
export interface AuthStep {
  id: string;
  symbolId?: string;
  qualifiedName: string;
  range: SourceRange;
  kind: string;
  mechanism: string;
  scope: string;
  applicability: string;
  onFailure: string;
  bindsObjectToCaller: string;
  expanded: string;
  calls: Call[];
  snippet?: Snippet;
}
export interface DataAccess {
  id: string;
  callId: string;
  operation: string;
  persistenceApi: string;
  object: { name: string; symbolId?: string; store?: string };
  ownershipEvidence: {
    inPredicate: string;
    stampedOnWrite: string;
    ownerFields: string[];
    identityBindingIds: string[];
  };
  paramFlows: { entryParamId: string; field: string; confidence: string }[];
  writtenFields: { field: string; source: string }[];
  snippet?: Snippet;
}
export interface Route {
  id: string;
  httpMethod: string;
  pathTemplate: string;
  language: string;
  framework: string;
  handler: { symbolId: string; qualifiedName: string; range: SourceRange };
  registration: { range: SourceRange; snippet?: Snippet };
  authChain: AuthStep[];
  callGraph: Call[];
  dataAccesses: DataAccess[];
  budget: {
    coverage: { authChain: string; callGraph: string; dataFlow: string };
    omitted: { id: string; reason: string; callId?: string; detail: string }[];
  };
}
export interface GraphDocument {
  schemaVersion: string;
  illustrative: boolean;
  note?: string;
  repo: { name: string; revision: string; vcs: string; remote?: string };
  languages: string[];
  frameworks: string[];
  generatedAt: string;
  symbolIndex: SymbolDefinition[];
  routes: Route[];
  unresolvedGaps: {
    id: string;
    kind: string;
    support: string;
    detail: string;
  }[];
}
export type NodeKind =
  | 'symbol'
  | 'route'
  | 'auth'
  | 'call'
  | 'data'
  | 'gap'
  | 'group';
export interface EvidenceRef {
  routeId: string;
  callId: string;
  authStepId?: string;
}
export interface GraphNode {
  id: string;
  name: string;
  subtitle: string;
  kind: NodeKind;
  children: string[];
  parent?: string;
  groupId?: string;
  route?: Route;
  call?: Call;
  symbol?: SymbolDefinition;
  range?: SourceRange;
  accesses: { route: Route; access: DataAccess }[];
  authSteps: { route: Route; step: AuthStep }[];
  evidence?: EvidenceRef;
  groupedRoutes?: Route[];
  sourceFile?: string;
  canonical?: boolean;
}
export interface GraphEdge {
  id: string;
  from: string;
  to: string;
  kind: 'call' | 'context' | 'unresolved' | 'definition';
  evidence: EvidenceRef[];
  aggregated?: boolean;
}
export interface SourceGroup {
  id: string;
  file: string;
  name: string;
  members: string[];
}
export interface AtlasGraph {
  document: GraphDocument;
  nodes: Map<string, GraphNode>;
  baseIds: string[];
  groups: SourceGroup[];
  edges: GraphEdge[];
  defaultId: string;
}
export interface Point {
  x: number;
  y: number;
}
export interface Camera extends Point {
  scale: number;
}
