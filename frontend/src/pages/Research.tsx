import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { patch, post } from "../api";
import { Badge, Card, Empty, ErrorBox, ExtLink, Field, KV, Modal, Notice, PageHeader, Spinner } from "../components/ui";
import { ago, dt, num } from "../format";
import { useApi } from "../hooks";

export default function Research() {
  const { data: sources, reload } = useApi<any[]>("/sources", { poll: 30000 });
  const { data: biz } = useApi<any[]>("/businesses");
  const { data: runs } = useApi<any[]>("/runs?limit=40", { poll: 15000 });
  const [cfg, setCfg] = useState<any | null>(null);
  const names = Object.fromEntries((biz || []).map((b) => [b.id, b.name]));
  const proposed = (sources || []).filter((s) => s.status === "proposed");
  const active = (sources || []).filter((s) => s.status !== "proposed");
  return (
    <div className="space-y-4">
      <PageHeader title="Research engine" sub="Discover → Retrieve → Parse → Extract → Verify → Deduplicate → Score → Qualify → Insert → Monitor → Recommend"
        actions={<button className="btn btn-primary" onClick={async () => { await post("/jobs/research-cycle"); alert("Research cycle queued."); }}>Run full cycle</button>} />
      <Card title="Sources" pad={false}>
        {!sources ? <Spinner /> : (
          <div className="overflow-x-auto"><table className="table">
            <thead><tr><th>Source</th><th className="hidden md:table-cell">Business</th><th>Status</th><th>Last success</th><th></th></tr></thead>
            <tbody>{active.map((s) => (
              <tr key={s.id}>
                <td><div className="font-medium">{s.name}</div><div className="text-[11px] text-slate-500">{s.adapter} · {s.official ? "official publisher" : "non-official"} · <ExtLink href={s.url}>link</ExtLink></div>
                  {s.last_error && <div className="text-[11px] text-danger">{s.last_error}</div>}</td>
                <td className="hidden text-xs text-slate-400 md:table-cell">{names[s.business_id]}</td>
                <td><Badge tone={!s.enabled ? "neutral" : s.status === "active" ? "good" : "warn"}>{s.enabled ? s.status.replace(/_/g, " ") : "disabled"}</Badge></td>
                <td className="text-xs text-slate-400">{ago(s.last_success_at)}</td>
                <td className="whitespace-nowrap"><button className="btn btn-sm mr-1" onClick={async () => { await post(`/sources/${s.id}/run`); reload(); }}>Run</button>
                  <button className="btn btn-sm" onClick={async () => { try { await patch(`/sources/${s.id}`, { enabled: !s.enabled }); reload(); } catch (e: any) { alert(e.message); } }}>{s.enabled ? "Disable" : "Enable"}</button></td>
              </tr>
            ))}</tbody>
          </table></div>
        )}
      </Card>
      <Card title={`Proposed sources (${proposed.length}) — found by the Source Discovery Agent or awaiting review`} pad={false}>
        {!proposed.length ? <Empty>No proposals. Discovery runs weekly against the Socrata open-data catalog.</Empty> : (
          <ul>{proposed.map((s) => (
            <li key={s.id} className="flex flex-wrap items-start justify-between gap-2 border-b border-ink-800 px-4 py-3 last:border-0">
              <div className="min-w-0"><div className="text-sm font-medium">{s.name}</div>
                <div className="text-xs text-slate-500">{names[s.business_id]} · {s.adapter} · <ExtLink href={s.url}>view dataset</ExtLink></div>
                <div className="text-xs text-slate-500">{s.access_notes}</div></div>
              <button className="btn btn-sm" onClick={() => setCfg(s)}>Review &amp; enable</button>
            </li>
          ))}</ul>
        )}
      </Card>
      <Card title="Recent runs" pad={false}>
        {!runs ? <Spinner /> : !runs.length ? <Empty>No runs yet.</Empty> : (
          <div className="overflow-x-auto"><table className="table">
            <thead><tr><th>Run</th><th>Source</th><th>Status</th><th>Retrieved</th><th>New</th><th>Updated</th><th>Qualified</th><th>Rejected</th></tr></thead>
            <tbody>{runs.map((r) => (
              <tr key={r.id}>
                <td><Link className="link" to={`/runs/${r.id}`}>#{r.id}</Link><div className="text-[11px] text-slate-500">{dt(r.started_at)}</div></td>
                <td className="text-xs text-slate-400">{(sources || []).find((s) => s.id === r.source_id)?.name || r.source_id}</td>
                <td><Badge tone={r.status === "succeeded" ? "good" : r.status === "partial" ? "warn" : r.status === "running" ? "info" : "bad"}>{r.status}</Badge></td>
                {["retrieved", "new", "updated", "qualified", "rejected"].map((k) => <td key={k} className="num">{num(r.stats?.[k])}</td>)}
              </tr>
            ))}</tbody>
          </table></div>
        )}
      </Card>
      {cfg && <ConfigureSource s={cfg} onClose={() => { setCfg(null); reload(); }} />}
    </div>
  );
}

function ConfigureSource({ s, onClose }: { s: any; onClose: () => void }) {
  const profile = s.config.profile;
  const keys = profile === "building_permit" ? ["address", "work_type", "description", "value", "date", "contractor"]
    : profile === "warn_notice" ? ["entity", "city", "count", "deadline", "date"] : ["owner", "filter_field", "amount", "address", "city", "date"];
  const [fields, setFields] = useState<Record<string, string>>(s.config.fields || {});
  const [jur, setJur] = useState(s.config.jurisdiction || "");
  const [err, setErr] = useState<string | null>(null);
  const cols: string[] = s.config.columns || [];
  return (
    <Modal open onClose={onClose} title="Configure proposed source" wide>
      <div className="space-y-3">
        <Notice>Map the dataset's columns to Executive Hub fields. The source stays disabled until you enable it. Records will be labelled with this dataset as their origin.</Notice>
        <KV k="Dataset" v={<ExtLink href={s.url}>{s.name}</ExtLink>} />
        <KV k="Profile" v={profile} />
        <Field label="Jurisdiction (2-letter)"><input className="input" maxLength={2} value={jur} onChange={(e) => setJur(e.target.value.toUpperCase())} /></Field>
        <div className="grid gap-2 sm:grid-cols-2">
          {keys.map((k) => (
            <Field key={k} label={k}>
              <select className="input" value={fields[k] || ""} onChange={(e) => setFields({ ...fields, [k]: e.target.value })}>
                <option value="">— none —</option>
                {cols.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </Field>
          ))}
        </div>
        <ErrorBox error={err} />
        <button className="btn btn-primary w-full" onClick={async () => {
          setErr(null);
          try {
            const clean = Object.fromEntries(Object.entries(fields).filter(([, v]) => v));
            await patch(`/sources/${s.id}`, { fields: clean, jurisdiction: jur || undefined });
            await patch(`/sources/${s.id}`, { enabled: true });
            onClose();
          } catch (ex: any) { setErr(ex.message); }
        }}>Save mapping &amp; enable</button>
      </div>
    </Modal>
  );
}

export function RunDetail() {
  const { id } = useParams();
  const { data: r, error } = useApi<any>(`/runs/${id}`, { poll: 10000 });
  if (error) return <ErrorBox error={error} />;
  if (!r) return <Spinner />;
  return (
    <div className="space-y-4">
      <PageHeader title={`Research run #${r.id}`} sub={`${dt(r.started_at)} → ${dt(r.finished_at)}`} />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Result">
          <KV k="Status" v={<Badge tone={r.status === "succeeded" ? "good" : r.status === "partial" ? "warn" : "bad"}>{r.status}</Badge>} />
          {Object.entries(r.stats || {}).map(([k, v]) => <KV key={k} k={k.replace(/_/g, " ")} v={<span className="num">{String(v)}</span>} />)}
          {r.error && <p className="mt-2 text-sm text-danger">{r.error}</p>}
        </Card>
        <Card title="Limitations recorded" className="lg:col-span-2">
          {r.limitations?.length ? <ul className="ml-4 list-disc text-sm text-warn">{r.limitations.map((l: string, i: number) => <li key={i}>{l}</li>)}</ul> : <p className="text-sm text-slate-500">None.</p>}
        </Card>
      </div>
      <Card title="Stage audit trail" pad={false}>
        <ul>{r.events.map((e: any, i: number) => (
          <li key={i} className="flex gap-3 border-b border-ink-800 px-4 py-2 text-sm last:border-0">
            <span className="num w-24 shrink-0 text-xs text-slate-500">{dt(e.at)}</span>
            <Badge tone={e.status === "ok" ? "good" : e.status === "error" ? "bad" : "warn"}>{e.stage}</Badge>
            <span className="min-w-0 break-words text-slate-300">{e.message}{e.data?.urls && <div className="mt-1 text-[11px] text-slate-500">{e.data.urls.map((u: string) => <div key={u} className="truncate">{u}</div>)}</div>}</span>
          </li>
        ))}</ul>
      </Card>
    </div>
  );
}
