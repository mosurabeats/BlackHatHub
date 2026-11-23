import { useState } from "react";
import { patch, post } from "../api";
import { Badge, Card, Empty, Field, KV, Modal, PageHeader, Spinner, StatusDot, Tabs } from "../components/ui";
import { ago, dt } from "../format";
import { useApi } from "../hooks";

export default function System() {
  const [tab, setTab] = useState("health");
  return (
    <div className="space-y-4">
      <PageHeader title="System" sub="Workers, jobs, schedules, backups and the audit log." />
      <Tabs tabs={[["health", "Health"], ["jobs", "Jobs"], ["schedules", "Schedules"], ["backups", "Backups"], ["audit", "Audit log"]]} active={tab} onChange={setTab} />
      {tab === "health" && <Health />}
      {tab === "jobs" && <Jobs />}
      {tab === "schedules" && <Schedules />}
      {tab === "backups" && <Backups />}
      {tab === "audit" && <Audit />}
    </div>
  );
}

function Health() {
  const { data: h } = useApi<any>("/system/health", { poll: 15000 });
  if (!h) return <Spinner />;
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      <Card title="Scheduler & workers">
        <KV k="Status" v={<span className="flex items-center gap-2"><StatusDot ok={h.scheduler.alive} />{h.scheduler.alive ? "running" : "not running"}</span>} />
        <KV k="Last heartbeat" v={ago(h.scheduler.last_beat_at)} />
        <KV k="Worker" v={<span className="num text-xs">{h.scheduler.worker_id || "—"}</span>} />
        <KV k="Missed scheduled runs (host offline)" v={h.missed_schedule_runs} />
        <KV k="Jobs recovered after restart" v={h.jobs.recovered_total} />
      </Card>
      <Card title="Jobs">
        <KV k="Running" v={h.jobs.running} />
        <KV k="Queued / retrying" v={h.jobs.queued} />
        <KV k="Succeeded (24h)" v={h.jobs.succeeded_24h} />
        <KV k="Failed (24h)" v={<span className={h.jobs.failed_24h ? "text-danger" : ""}>{h.jobs.failed_24h}</span>} />
        <KV k="Sources needing attention" v={h.sources_needing_attention} />
      </Card>
      <Card title="Integrations">
        <KV k="Anthropic API" v={<Badge tone={h.ai.anthropic_configured ? "good" : "neutral"}>{h.ai.anthropic_configured ? "configured" : "not configured"}</Badge>} />
        <KV k="OpenAI API" v={<Badge tone={h.ai.openai_configured ? "good" : "neutral"}>{h.ai.openai_configured ? "configured" : "not configured"}</Badge>} />
        <KV k="SAM.gov API key" v={<Badge tone={h.credentials.sam_gov ? "good" : "neutral"}>{h.credentials.sam_gov ? "configured" : "missing"}</Badge>} />
        <KV k="Socrata app token" v={<Badge tone={h.credentials.socrata_app_token ? "good" : "neutral"}>{h.credentials.socrata_app_token ? "configured" : "optional"}</Badge>} />
        <KV k="Database" v={h.database.engine} />
        <KV k="Last backup" v={h.last_backup ? ago(h.last_backup.created_at) : "none"} />
      </Card>
    </div>
  );
}

function Jobs() {
  const [status, setStatus] = useState("");
  const { data, reload } = useApi<any[]>(`/jobs?limit=150${status ? `&status=${status}` : ""}`, { poll: 10000 });
  const [open, setOpen] = useState<any | null>(null);
  return (
    <Card pad={false} title="Jobs" actions={<select className="input w-36 py-1 text-xs" value={status} onChange={(e) => setStatus(e.target.value)}>
      <option value="">All</option>{["queued", "running", "retry_wait", "succeeded", "failed", "cancelled"].map((s) => <option key={s}>{s}</option>)}</select>}>
      {!data ? <Spinner /> : !data.length ? <Empty>No jobs.</Empty> : (
        <div className="overflow-x-auto"><table className="table">
          <thead><tr><th>ID</th><th>Type</th><th>Status</th><th>Attempts</th><th>Created</th><th>Finished</th><th></th></tr></thead>
          <tbody>{data.map((j) => (
            <tr key={j.id}>
              <td className="num"><button className="link" onClick={() => setOpen(j)}>#{j.id}</button></td>
              <td>{j.job_type}{j.recovered && <Badge tone="info">recovered</Badge>}<div className="text-[11px] text-slate-500">{j.triggered_by}</div></td>
              <td><Badge tone={j.status === "succeeded" ? "good" : j.status === "failed" ? "bad" : j.status === "running" ? "info" : "neutral"}>{j.status}</Badge>{j.error && <div className="max-w-xs truncate text-[11px] text-danger">{j.error}</div>}</td>
              <td className="num">{j.attempts}/{j.max_attempts}</td>
              <td className="text-xs">{dt(j.created_at)}</td>
              <td className="text-xs">{dt(j.finished_at)}</td>
              <td className="whitespace-nowrap">
                {["queued", "running", "retry_wait"].includes(j.status) && <button className="btn btn-sm" onClick={async () => { await post(`/jobs/${j.id}/cancel`); reload(); }}>Cancel</button>}
                {["failed", "cancelled"].includes(j.status) && <button className="btn btn-sm" onClick={async () => { await post(`/jobs/${j.id}/retry`); reload(); }}>Retry</button>}
              </td>
            </tr>
          ))}</tbody>
        </table></div>
      )}
      <Modal open={!!open} onClose={() => setOpen(null)} title={`Job #${open?.id}`} wide>
        <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap text-xs text-slate-300">{JSON.stringify(open, null, 2)}</pre>
      </Modal>
    </Card>
  );
}

function Schedules() {
  const { data, reload } = useApi<any[]>("/schedules", { poll: 30000 });
  const [edit, setEdit] = useState<Record<number, string>>({});
  return (
    <Card pad={false} title="Schedules">
      {!data ? <Spinner /> : (
        <div className="overflow-x-auto"><table className="table">
          <thead><tr><th>Schedule</th><th>Every (min)</th><th>Next run</th><th>Last run</th><th>Missed</th><th></th></tr></thead>
          <tbody>{data.map((s) => (
            <tr key={s.id}>
              <td>{s.name}<div className="text-[11px] text-slate-500">{s.job_type}</div></td>
              <td><input className="input w-24 py-1 text-xs" value={edit[s.id] ?? String(s.interval_minutes)} onChange={(e) => setEdit({ ...edit, [s.id]: e.target.value })}
                onBlur={async () => { if (edit[s.id] && Number(edit[s.id]) !== s.interval_minutes) { try { await patch(`/schedules/${s.id}`, { interval_minutes: Number(edit[s.id]) }); reload(); } catch (e: any) { alert(e.message); } } }} /></td>
              <td className="text-xs">{s.enabled ? ago(s.next_run_at) : "paused"}</td>
              <td className="text-xs">{ago(s.last_run_at)}</td>
              <td className="num">{s.missed_runs}</td>
              <td className="whitespace-nowrap">
                <button className="btn btn-sm mr-1" onClick={async () => { await post(`/schedules/${s.id}/run-now`); reload(); }}>Run now</button>
                <button className="btn btn-sm" onClick={async () => { await patch(`/schedules/${s.id}`, { enabled: !s.enabled }); reload(); }}>{s.enabled ? "Pause" : "Resume"}</button>
              </td>
            </tr>
          ))}</tbody>
        </table></div>
      )}
    </Card>
  );
}

function Backups() {
  const { data, reload } = useApi<any[]>("/system/backups");
  const [restore, setRestore] = useState<string | null>(null);
  const [pw, setPw] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  return (
    <Card pad={false} title="Database backups" actions={<button className="btn btn-sm btn-primary" onClick={async () => { await post("/system/backups"); reload(); }}>Back up now</button>}>
      {!data ? <Spinner /> : !data.length ? <Empty>No backups yet. A backup runs daily.</Empty> : (
        <table className="table"><thead><tr><th>File</th><th>Created</th><th className="text-right">Size</th><th></th></tr></thead>
          <tbody>{data.map((b) => (
            <tr key={b.name}><td className="num text-xs">{b.name}</td><td className="text-xs">{dt(b.created_at)}</td><td className="num text-right text-xs">{(b.size_bytes / 1024 / 1024).toFixed(1)} MB</td>
              <td><button className="btn btn-sm" onClick={() => setRestore(b.name)}>Restore…</button></td></tr>
          ))}</tbody></table>
      )}
      <Modal open={!!restore} onClose={() => setRestore(null)} title="Restore backup">
        <div className="space-y-3">
          <p className="text-sm text-slate-400">Restoring replaces the current database with <span className="num">{restore}</span>. A safety backup of the current state is taken first.</p>
          <Field label="Confirm with your password"><input className="input" type="password" value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
          {msg && <p className="text-sm text-warn">{msg}</p>}
          <button className="btn btn-danger w-full" disabled={!pw} onClick={async () => {
            try { const r = await post("/system/backups/restore", { name: restore, password: pw }); setMsg(`Restored. Safety backup: ${r.safety_backup}. Reloading…`); setTimeout(() => window.location.reload(), 1500); } catch (e: any) { setMsg(e.message); }
          }}>Restore</button>
        </div>
      </Modal>
    </Card>
  );
}

function Audit() {
  const { data } = useApi<any[]>("/audit?limit=300");
  return (
    <Card pad={false} title="Audit log">
      {!data ? <Spinner /> : (
        <div className="overflow-x-auto"><table className="table">
          <thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Target</th><th>Detail</th></tr></thead>
          <tbody>{data.map((a) => (
            <tr key={a.id}><td className="whitespace-nowrap text-xs">{dt(a.at)}</td><td className="text-xs">{a.actor}</td><td className="text-xs">{a.action}</td>
              <td className="text-xs text-slate-500">{a.target_type} {a.target_id}</td><td className="max-w-md truncate text-[11px] text-slate-500">{JSON.stringify(a.detail)}</td></tr>
          ))}</tbody>
        </table></div>
      )}
    </Card>
  );
}
