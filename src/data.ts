import aegra from '../docs/code-graph-example-aegra.json';
import papertrail from '../docs/code-graph-example.json';
import { adaptGraph } from './graph/adapter';
import type { GraphDocument } from './graph/types';

export const datasets = {
  aegra: adaptGraph(aegra as GraphDocument),
  papertrail: adaptGraph(papertrail as GraphDocument),
};
export type DatasetId = keyof typeof datasets;
