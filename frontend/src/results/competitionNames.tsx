import { createContext, useContext } from 'react';
import type { Competition } from './generated/artifacts.ts';

export const CompetitionCatalog = createContext<readonly Competition[]>([]);
export function competitionDisplayName(values: readonly Competition[], id: string) {
  return values.find((value) => value.id === id)?.name ?? id;
}
export function useCompetitionName() {
  const values = useContext(CompetitionCatalog);
  return (id: string) => competitionDisplayName(values, id);
}
