import { useState } from "react";
import { Link } from "react-router-dom";
import { patch } from "../api";
import { Badge, Card, Empty, PageHeader, Spinner } from "../components/ui";
import { dt } from "../format";
import { useApi } from "../hooks";

export default function Compliance() {
  const [status, setStatus] = useState("open");
  const { data, reload } = useApi<any[]>(`/compliance/alerts?status=${status}`);
  return (
    <div className="space-y-4">
      <PageHeader title="Compliance & regulatory alerts" sub="Raised by the Compliance Analyst. Rules-based; it flags uncertainty rather than deciding legality."
        actions={<select className="input w-40" value={status} onChange={(e) => setStatus(e.target.value)}><option value="open">Open</option><option value="acknowledged">Acknowledged</option><option value="resolved">Resolved</option></select>} />
      <Card pad={false}>
        {!data ? <Spinner /> : !data.length ? <Empty>No {status} alerts.</Empty> : (
          <ul>{data.map((a) => (
            <li key={a.id} className="flex flex-wrap items-start justify-between gap-3 border-b border-ink-800 px-4 py-3 last:border-0">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <Badge tone={a.severity === "critical" ? "bad" : a.severity === "warning" ? "warn" : "info"}>{a.severity}</Badge>
                  <span className="font-medium">{a.title}</span>
                </div>
                <p className="mt-1 text-xs text-slate-400">{a.detail}</p>
                <div className="mt-1 text-[11px] text-slate-600">{dt(a.created_at)} · {a.code}
                  {a.jurisdiction_code && <> · <Link className="link" to={`/jurisdictions?code=${a.jurisdiction_code}`}>{a.jurisdiction_code}</Link></>}
                  {a.opportunity_id && <> · <Link className="link" to={`/o/${a.opportunity_id}`}>opportunity</Link></>}
                </div>
              </div>
              <div className="flex gap-1">
                {a.status !== "acknowledged" && <button className="btn btn-sm" onClick={async () => { await patch(`/compliance/alerts/${a.id}`, { status: "acknowledged" }); reload(); }}>Acknowledge</button>}
                {a.status !== "resolved" && <button className="btn btn-sm" onClick={async () => { await patch(`/compliance/alerts/${a.id}`, { status: "resolved" }); reload(); }}>Resolve</button>}
              </div>
            </li>
          ))}</ul>
        )}
      </Card>
    </div>
  );
}
