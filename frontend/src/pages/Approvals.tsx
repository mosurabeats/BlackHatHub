import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { post } from "../api";
import { Badge, Card, Empty, ErrorBox, Field, KV, Modal, Notice, PageHeader, Spinner } from "../components/ui";
import { dt, money } from "../format";
import { useApi } from "../hooks";

export default function Approvals() {
  const [sp, setSp] = useSearchParams();
  const [status, setStatus] = useState("pending");
  const { data, reload } = useApi<any[]>(`/approvals?status=${status}`);
  const openId = sp.get("open");
  return (
    <div className="space-y-4">
      <PageHeader title="Approvals" sub="Every external or consequential action needs a specific, single-use approval." actions={
        <select className="input w-40" value={status} onChange={(e) => setStatus(e.target.value)}>
          {["pending", "approved", "executed", "rejected", "cancelled", "expired"].map((s) => <option key={s}>{s}</option>)}
        </select>} />
      <Card pad={false}>
        {!data ? <Spinner /> : !data.length ? <Empty>No {status} approvals.</Empty> : (
          <ul>{data.map((a) => (
            <li key={a.id} className="border-b border-ink-800 last:border-0">
              <button className="block w-full px-4 py-3 text-left hover:bg-ink-850" onClick={() => setSp({ open: String(a.id) })}>
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="num text-slate-500">#{a.id}</span>
                  <Badge tone="warn">{a.action_type.replace(/_/g, " ")}</Badge>
                  {a.compliance_blockers?.length > 0 && <Badge tone="bad">compliance blockers</Badge>}
                  <span className="text-xs text-slate-500">requested by {a.requested_by} · {dt(a.created_at)}</span>
                </div>
                <div className="mt-1 text-sm text-slate-200">{a.proposed_action}</div>
              </button>
            </li>
          ))}</ul>
        )}
      </Card>
      {openId && <ApprovalDetail id={Number(openId)} onClose={() => { setSp({}); reload(); }} />}
    </div>
  );
}

function ApprovalDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { data: a, reload } = useApi<any>(`/approvals/${id}`);
  const [note, setNote] = useState("");
  const [confirmText, setConfirmText] = useState(false);
  const [result, setResult] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const act = async (fn: () => Promise<any>) => {
    setErr(null);
    try { await fn(); await reload(); } catch (ex: any) { setErr(ex.message); }
  };
  return (
    <Modal open onClose={onClose} title={`Approval #${id}`} wide>
      {!a ? <Spinner /> : (
        <div className="space-y-4">
          <div>
            <div className="h-label mb-1">Exact proposed action</div>
            <div className="rounded-md border border-warn/40 bg-warn/5 p-3 text-sm">{a.proposed_action}</div>
            <div className="mt-1 text-[11px] text-slate-500 num">action hash {a.action_hash.slice(0, 16)}… — approval authorizes only this exact action, once.</div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div><div className="h-label mb-1">Justification</div><p className="text-sm text-slate-300">{a.justification}</p></div>
            <div><div className="h-label mb-1">Expected benefit</div><p className="text-sm text-slate-300">{a.expected_benefit}</p></div>
            <div><div className="h-label mb-1">Risks</div><p className="text-sm text-slate-300">{a.risks}</p></div>
            <div><div className="h-label mb-1">Evidence</div><p className="break-words text-xs text-slate-400">{a.evidence_summary}</p></div>
          </div>
          <div className="grid gap-x-8 sm:grid-cols-2">
            <KV k="Status" v={<Badge tone={a.status === "pending" ? "warn" : a.status === "approved" ? "good" : "neutral"}>{a.status}</Badge>} />
            <KV k="Estimated cost" v={money(a.estimated_cost_usd, 2)} />
            <KV k="Requested by" v={a.requested_by} />
            <KV k="Expires" v={dt(a.expires_at)} />
            {a.opportunity && <KV k="Opportunity" v={<Link className="link" to={`/o/${a.opportunity.id}`}>{a.opportunity.title.slice(0, 60)}</Link>} />}
            {a.decided_by && <KV k="Decided" v={`${a.decided_by} · ${dt(a.decided_at)}`} />}
          </div>
          {a.current_compliance_blockers?.length > 0 && (
            <Notice tone="warn"><b>Cannot approve until resolved:</b><ul className="ml-4 list-disc">{a.current_compliance_blockers.map((b: string) => <li key={b}>{b}</li>)}</ul></Notice>
          )}
          <ErrorBox error={err} />
          {a.status === "pending" && (
            <div className="space-y-2 border-t border-ink-700 pt-3">
              <Field label="Decision note (optional)"><input className="input" value={note} onChange={(e) => setNote(e.target.value)} /></Field>
              <label className="flex items-start gap-2 text-sm text-slate-300">
                <input type="checkbox" className="mt-1" checked={confirmText} onChange={(e) => setConfirmText(e.target.checked)} />
                I have read the exact action above and authorize it once. This does not authorize any other or future action.
              </label>
              <div className="flex gap-2">
                <button className="btn btn-primary flex-1" disabled={!confirmText} onClick={() => act(() => post(`/approvals/${id}/approve`, { note, confirm_hash: a.action_hash }))}>Approve this action</button>
                <button className="btn btn-danger flex-1" onClick={() => act(() => post(`/approvals/${id}/reject`, { note }))}>Reject</button>
              </div>
            </div>
          )}
          {a.status === "approved" && (
            <div className="space-y-2 border-t border-ink-700 pt-3">
              <Notice>Executive Hub has no outbound messaging, filing or payment integrations enabled, so approved actions are carried out by you. Record the outcome here to close the approval.</Notice>
              <Field label="What was done (result)"><textarea className="input" rows={2} value={result} onChange={(e) => setResult(e.target.value)} /></Field>
              <div className="flex gap-2">
                <button className="btn btn-primary flex-1" disabled={result.length < 3} onClick={() => act(() => post(`/approvals/${id}/executed`, { result }))}>Mark executed</button>
                <button className="btn flex-1" onClick={() => act(() => post(`/approvals/${id}/cancel`))}>Cancel approval</button>
              </div>
            </div>
          )}
          {a.execution_result && <KV k="Execution result" v={a.execution_result} />}
        </div>
      )}
    </Modal>
  );
}
