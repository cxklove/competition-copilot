import type { Evidence } from './generated/artifacts.ts';
import { SourceMetadata } from './SourceMetadata.tsx';

export function EvidenceList({ evidence }: { evidence: Evidence[] }) {
  return evidence.length ? (
    <ul className="evidence-list" aria-label="证据">
      {evidence.map((item, index) => (
        <li key={`${index}-${item.code}`}>
          <strong>{item.code}</strong>
          <p>{item.message}</p>
          {item.field && (
            <p>
              字段：{item.field} {item.value != null && <span>· {String(item.value)}</span>}
            </p>
          )}
          {item.source ? (
            <SourceMetadata source={item.source} />
          ) : (
            <p className="unavailable">未提供来源元数据。</p>
          )}
        </li>
      ))}
    </ul>
  ) : (
    <p className="unavailable">无可用证据正文；未补造依据或来源。</p>
  );
}
