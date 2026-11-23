import { FormEvent, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { post } from "../api";
import { Badge, Card, Empty, ErrorBox, EstimateTag, ExtLink, Field, KV, Modal, Notice, PageHeader, ScoreBar, Spinner, StageBadge, stageLabel } from "../components/ui";
import { day, dt, money, pct } from "../format";
import { useApi } from "../hooks";

const OWNER_STAGES = ["contacted", "negotiating", "active", "won", "lost"];
const ACTIONS = [
  "contact_prospect", "send_external_message", "publish_content", "submit_legal_document", "financial_commitment",
  "purchase_dataset", "enter_agreement", "initiate_payment", "create_external_account", "file_claim",
];

export default function Opportunity() {
  const { id } = useParams();
  const { data: o, error, reload } = useApi<any>(`/opportunities/${id}`);
  const [moveOpen, setMoveOpen] = useState(false);
  const [apOpen, setApOpen] = useState(false);
  const [note, setNote] = useState("");
  if (error) return <ErrorBox error={error} />;
  if (!o) return <Spinner />;

  return (
    <div className="space-y-4">
      <PageHeader
        title={o.title}
        sub={<span><Link className="link" to={`/b/${o.business.slug}`}>{o.business.name}</Link> · first seen {day(o.first_seen_at)} · {o.original_source}</span>}
        actions={
          <>
            <button className="btn" onClick={async () => { try { await post(`/opportunities/${o.id}/rescore`); reload(); } catch (e: any) { alert(e.message); } }}>Re-score</button>
            <button className="btn" onClick={() => setMoveOpen(true)}>Update stage</button>
            <button className="btn btn-primary" onClick={() => setApOpen(true)}>Request approval…</button>
          </>
        }
      />
      {o.is_sample && <Notice tone="warn">This is SAMPLE data, not a real discovery.</Notice>}
      {o.compliance_blockers.length > 0 && (
        <Notice tone="warn">
          <b>External action blocked until resolved:</b>
          <ul className="ml-4 mt-1 list-disc">{o.compliance_blockers.map((b: string) => <li key={b}>{b}</li>)}</ul>
        </Notice>
      )}

      <div className="grid gap-4 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">
          <Card title="Business opportunity">
            <p className="text-sm leading-relaxed text-slate-300">{o.summary}</p>
            <div className="mt-3 grid gap-x-8 sm:grid-cols-2">
              <KV k="Stage" v={<StageBadge stage={o.stage} />} />
              <KV k="Entity" v={o.entity_name || "—"} />
              <KV k="Jurisdiction" v={o.jurisdiction_code ? <Link className="link" to={`/jurisdictions?code=${o.jurisdiction_code}`}>{o.jurisdiction_code}</Link> : "—"} />
              <KV k="Location" v={o.location || "—"} />
              <KV k="Deadline" v={day(o.deadline)} />
              <KV k="Category" v={o.category || "—"} />
            </div>
          </Card>

          <Card title="Commercial evaluation">
            <div className="grid gap-x-8 sm:grid-cols-2">
              <KV k="Score" v={<ScoreBar score={o.score} />} />
              <KV k="Confidence" v={pct(o.confidence)} />
              <KV k="Reported / published value" v={<span className="num">{money(o.reported_value, 2)}</span>} />
              <KV k={<span>Estimated revenue <EstimateTag /></span>} v={<span className="num text-warn">{money(o.estimated_value, 2)}</span>} />
              <KV k="Estimated cost to pursue" v={<span className="num">{money(o.estimated_cost, 2)}</span>} />
              <KV k={<span>Expected value <EstimateTag /></span>} v={<span className="num text-warn">{money(o.expected_value, 2)}</span>} />
            </div>
            <p className="mt-3 rounded-md bg-ink-850 p-2 text-xs text-slate-400"><b>Basis:</b> {o.estimated_value_basis || "—"}</p>
            {Object.keys(o.score_breakdown || {}).length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {Object.entries(o.score_breakdown).map(([k, v]) => <Badge key={k}>{k.replace(/_/g, " ")}: {typeof v === "number" ? v.toFixed(2) : String(v)}</Badge>)}
              </div>
            )}
          </Card>

          <Card title={`Supporting research & evidence (${o.evidence.length})`} pad={false}>
            {!o.evidence.length ? <Empty>No evidence recorded.</Empty> : (
              <ul>{o.evidence.map((e: any) => (
                <li key={e.id} className="border-b border-ink-800 px-4 py-3 last:border-0">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <Badge tone={e.is_ai_generated ? "ai" : e.supports_verification ? "good" : "neutral"}>{e.is_ai_generated ? "AI analysis — not verified" : e.kind.replace(/_/g, " ")}</Badge>
                    <span className="font-medium">{e.title}</span>
                  </div>
                  <div className="mt-1 text-xs text-slate-500">Retrieved {dt(e.retrieved_at)} · <ExtLink href={e.url}>source</ExtLink>{e.content_hash && <span className="num"> · sha256 {e.content_hash.slice(0, 10)}…</span>}</div>
                  {e.excerpt && <p className="mt-1.5 line-clamp-4 whitespace-pre-wrap text-xs text-slate-400">{e.excerpt}</p>}
                </li>
              ))}</ul>
            )}
          </Card>

          <Card title="Pipeline history" pad={false}>
            <ul>{o.history.map((h: any) => (
              <li key={h.id} className="flex gap-3 border-b border-ink-800 px-4 py-2 text-sm last:border-0">
                <span className="num w-28 shrink-0 text-xs text-slate-500">{dt(h.at)}</span>
                <div className="min-w-0">
                  {h.event === "stage_change" ? <span>{h.from_stage ? `${stageLabel(h.from_stage)} → ` : ""}<b>{stageLabel(h.to_stage)}</b></span> : <span className="text-slate-300">{h.event}</span>}
                  <span className="ml-2 text-xs text-slate-500">{h.actor}</span>
                  {h.reason && <div className="text-xs text-slate-400">{h.reason}</div>}
                  {h.changes && Object.keys(h.changes).length > 0 && (
                    <div className="text-[11px] text-slate-500">{Object.entries(h.changes).map(([k, v]: any) => `${k}: ${v.from} → ${v.to}`).join("; ")}</div>
                  )}
                </div>
              </li>
            ))}</ul>
          </Card>
        </div>

        <div className="space-y-4">
          <Card title="Suggested action">
            <p className="text-sm text-slate-300">{o.recommended_action || "—"}</p>
          </Card>
          <Card title="Risks">
            {o.risks?.length ? <ul className="ml-4 list-disc space-y-1 text-sm text-slate-300">{o.risks.map((r: string) => <li key={r}>{r}</li>)}</ul> : <p className="text-sm text-slate-500">None recorded.</p>}
          </Card>
          <Card title="Regulatory considerations">
            <pre className="whitespace-pre-wrap font-sans text-sm text-slate-300">{o.regulatory_notes || "—"}</pre>
            {o.jurisdiction && (
              <div className="mt-2 text-xs text-slate-500">
                {o.jurisdiction.name}: rules <Badge tone={o.jurisdiction.compliance_review_status === "verified" ? "good" : "warn"}>{o.jurisdiction.compliance_review_status.replace(/_/g, " ")}</Badge> · operating <Badge>{o.jurisdiction.operating_status.replace(/_/g, " ")}</Badge>
              </div>
            )}
          </Card>
          <Card title="Provenance">
            <KV k="Original source" v={o.original_source} />
            <KV k="Source URL" v={<ExtLink href={o.source_url}>open</ExtLink>} />
            <KV k="Retrieved" v={dt(o.retrieved_at)} />
            <KV k="Last verified" v={dt(o.last_verified_at)} />
            <KV k="Verification" v={o.verification_status.replace(/_/g, " ")} />
            {o.data?.entity_check && <KV k="Entity registry check" v={<Badge tone={o.data.entity_check.status === "match" ? "good" : "warn"}>{o.data.entity_check.status}</Badge>} />}
            {o.data?.record_count > 1 && <KV k="Source records merged" v={o.data.record_count} />}
          </Card>
          <Card title={`Approvals (${o.approvals.length})`} pad={false}>
            {!o.approvals.length ? <Empty>None.</Empty> : <ul>{o.approvals.map((a: any) => (
              <li key={a.id} className="border-b border-ink-800 px-4 py-2 text-sm last:border-0"><Link className="link" to={`/approvals?open=${a.id}`}>#{a.id} {a.action_type.replace(/_/g, " ")}</Link> <Badge tone={a.status === "approved" ? "good" : a.status === "pending" ? "warn" : "neutral"}>{a.status}</Badge></li>
            ))}</ul>}
          </Card>
          <Card title="Contacts (public record)" pad={false}>
            {!o.contacts.length ? <Empty>None.</Empty> : <ul>{o.contacts.map((c: any) => <li key={c.id} className="border-b border-ink-800 px-4 py-2 text-sm last:border-0">{c.name} <span className="text-xs text-slate-500">{c.role}</span></li>)}</ul>}
          </Card>
          <Card title="Add note">
            <form onSubmit={async (e) => { e.preventDefault(); await post(`/opportunities/${o.id}/notes`, { text: note }); setNote(""); reload(); }} className="space-y-2">
              <textarea className="input" rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
              <button className="btn w-full" disabled={!note.trim()}>Save note</button>
            </form>
          </Card>
        </div>
      </div>
      <MoveModal open={moveOpen} onClose={() => setMoveOpen(false)} o={o} onDone={reload} />
      <ApprovalModal open={apOpen} onClose={() => setApOpen(false)} o={o} onDone={reload} />
    </div>
  );
}

function MoveModal({ open, onClose, o, onDone }: any) {
  const [stage, setStage] = useState("contacted");
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    try { await post(`/opportunities/${o.id}/transition`, { stage, reason }); onClose(); onDone(); } catch (ex: any) { setErr(ex.message); }
  };
  return (
    <Modal open={open} onClose={onClose} title="Update stage">
      <form onSubmit={submit} className="space-y-3">
        <p className="text-xs text-slate-500">Research stages are managed by the agents. External stages (Contacted onwards) require a previously approved outreach action.</p>
        <Field label="New stage"><select className="input" value={stage} onChange={(e) => setStage(e.target.value)}>{OWNER_STAGES.map((s) => <option key={s} value={s}>{stageLabel(s)}</option>)}</select></Field>
        <Field label="Reason"><textarea className="input" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        <ErrorBox error={err} />
        <button className="btn btn-primary w-full">Update</button>
      </form>
    </Modal>
  );
}

function ApprovalModal({ open, onClose, o, onDone }: any) {
  const [f, setF] = useState({ action_type: "contact_prospect", proposed_action: "", justification: "", expected_benefit: "", risks: "", estimated_cost_usd: "0" });
  const [err, setErr] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    try { await post(`/opportunities/${o.id}/request-approval`, { ...f, estimated_cost_usd: Number(f.estimated_cost_usd) }); onClose(); onDone(); } catch (ex: any) { setErr(ex.message); }
  };
  return (
    <Modal open={open} onClose={onClose} title="Request approval for a specific action" wide>
      <form onSubmit={submit} className="space-y-3">
        <p className="text-xs text-slate-500">An approval authorizes exactly this one action — never future actions.</p>
        <Field label="Action type"><select className="input" value={f.action_type} onChange={(e) => setF({ ...f, action_type: e.target.value })}>{ACTIONS.map((a) => <option key={a} value={a}>{a.replace(/_/g, " ")}</option>)}</select></Field>
        <Field label="Exact proposed action"><textarea className="input" rows={3} value={f.proposed_action} onChange={(e) => setF({ ...f, proposed_action: e.target.value })} /></Field>
        <Field label="Justification"><textarea className="input" rows={2} value={f.justification} onChange={(e) => setF({ ...f, justification: e.target.value })} /></Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Expected benefit"><textarea className="input" rows={2} value={f.expected_benefit} onChange={(e) => setF({ ...f, expected_benefit: e.target.value })} /></Field>
          <Field label="Risks"><textarea className="input" rows={2} value={f.risks} onChange={(e) => setF({ ...f, risks: e.target.value })} /></Field>
        </div>
        <Field label="Estimated cost (USD)"><input className="input" type="number" min="0" step="0.01" value={f.estimated_cost_usd} onChange={(e) => setF({ ...f, estimated_cost_usd: e.target.value })} /></Field>
        <ErrorBox error={err} />
        <button className="btn btn-primary w-full">Submit request</button>
      </form>
    </Modal>
  );
}
