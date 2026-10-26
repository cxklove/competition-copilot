import assert from 'node:assert/strict';
import test from 'node:test';
import type { Competition } from '../src/results/generated/artifacts.ts';
import { competitionDisplayName } from '../src/results/competitionNames.tsx';

test('shared name resolution preserves authoritative Chinese/English names and canonical identity', () => {
  const values: Competition[] = [
    { id: 'canonical-chinese', name: '正式赛事名称' },
    { id: 'canonical-english', name: 'Authoritative English Competition' },
  ];
  const before = JSON.stringify(values);
  assert.equal(competitionDisplayName(values, 'canonical-chinese'), '正式赛事名称');
  assert.equal(
    competitionDisplayName(values, 'canonical-english'),
    'Authoritative English Competition',
  );
  assert.equal(competitionDisplayName(values, 'unresolved-id'), 'unresolved-id');
  assert.equal(JSON.stringify(values), before);
  assert.equal(
    competitionDisplayName(
      [{ id: 'canonical-chinese', name: '更新后的正式名称' }],
      'canonical-chinese',
    ),
    '更新后的正式名称',
  );
});
