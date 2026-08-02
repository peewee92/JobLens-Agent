import type {ImportOutcome, RemoteStatus} from "@/lib/contracts";
import {formatImportOutcome, formatRemoteStatus} from "@/lib/format";

export function RemoteStatusPill({status}: {status: RemoteStatus}) {
  return (
    <span className={`status-pill status-${status}`}>
      {formatRemoteStatus(status)}
    </span>
  );
}

export function ImportOutcomePill({outcome}: {outcome: ImportOutcome}) {
  return (
    <span className={`status-pill status-${outcome}`}>
      {formatImportOutcome(outcome)}
    </span>
  );
}
