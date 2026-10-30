import { createContext, useContext } from 'react';
import type { Competition } from './generated/artifacts.ts';

type CompetitionName = Pick<Competition, 'id' | 'name'>;
export const CompetitionCatalog = createContext<readonly CompetitionName[]>([]);
export function competitionDisplayName(values: readonly CompetitionName[], id: string) {
  return values.find((value) => value.id === id)?.name ?? id;
}
export function useCompetitionName() {
  const values = useContext(CompetitionCatalog);
  return (id: string) => competitionDisplayName(values, id);
}
