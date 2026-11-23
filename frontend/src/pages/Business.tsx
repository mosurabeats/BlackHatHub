import { FormEvent, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { del, patch, post } from "../api";
import OpportunityTable from "../components/OpportunityTable";
import { Badge, Card, Empty, ErrorBox, EstimateTag, ExtLink, Field, KV, Modal, Notice, PageHeader, Spinner, Stat, STAGES, Tabs } from "../components/ui";
import { ago, day, dt, money, num } from "../format";
import { useApi } from "../hooks";

const TABS: [string, string][] = [
  ["overview", "Overview"],
  ["feed", "Research feed"],
  ["pipeline", "Pipeline"],
  ["crm", "CRM"],
  ["tasks", "Tasks"],
  ["finance", "Financials"],
  ["recs", "AI recommendations"],
  ["reports", "Reports"],
  ["automation", "Automation"],
];

export default function Business() {
  const { slug } = useParams();
  const [sp, setSp] = useSearchParams();
  const tab = sp.get("tab") || "overview";
  const { data: b, error, reload } = useApi<any>(`/businesses/${slug}`);
  if (error) return <ErrorBox error={error === "Not found" ? "Business not found (private ventures require the vault to be unlocked)." : error} />;
  if (!b) return <Spinner />;
  return (
    <div className="space-y-4">
      <PageHeader
        title={<span><span className="num mr-2 text-sm text-slate-500">{b.code}</span>{b.name}{b.is_private && <span className="ml-2 align-middle"><Badge tone="warn">private</Badge></span>}</span>}
        sub={b.description}
      />
      <Tabs tabs={TABS} active={tab} onChange={(k) => setSp({ tab: k })} />
      {tab === "overview" && <Overview b={b} />}
      {tab === "feed" && <Feed b={b} />}
      {tab === "pipeline" && <Pipeline b={b} />}
      {tab === "crm" && <Crm b={b} />}
      {tab === "tasks" && <Tasks b={b} />}
      {tab === "finance" && <BizFinance b={b} />}
      {tab === "recs" && <Recs b={b} />}
      {tab === "reports" && <Reports b={b} />}
      {tab === "automation" && <Automation b={b} onChange={reload} />}
    </div>
  );
}

function Overview({ b }: { b: any }) {
  const s = b.stats;
  const { data: top } = useApi<any>(`/opportunities?business=${b.slug}&open_only=true&limit=10`);
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Open opportunities" value={s.open_opportunities} />
        <Stat label="Qualified" value={s.stage_counts.qualified} tone="good" />
        <Stat label="Qualified exp. value" value={money(s.qualified_expected_value_estimate)} sub={<EstimateTag />} />
        <Stat label="Pending approvals" value={s.pending_approvals} tone={s.pending_approvals ? "warn" : undefined} />
        <Stat label="Open tasks" value={s.open_tasks} />
        <Stat label="Sources enabled" value={`${s.sources_enabled}/${s.sources}`} sub={s.last_run ? `last run ${ago(s.last_run.started_at)}` : "never run"} />
      </div>
      <Card title="Pipeline by stage">
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-6 lg:grid-cols-11">
          {STAGES.map(([k, label]) => (
            <Link key={k} to={`?tab=pipeline&stage=${k}`} className="rounded-md border border-ink-700 p-2 text-center hover:border-ink-500">
              <div className="num text-lg">{s.stage_counts[k]}</div>
              <div className="text-[10px] leading-tight text-slate-500">{label}</div>
            </Link>
          ))}
        </div>
      </Card>
      <Card title="Top open opportunities" pad={false}>
        {top ? <OpportunityTable items={top.items} /> : <Spinner />}
      </Card>
    </div>
  );
}

function Feed({ b }: { b: any }) {
  const { data: runs } = useApi<any[]>(`/runs?business_id=${b.id}&limit=25`, { poll: 20000 });
  const { data: recent } = useApi<any>(`/opportunities?business=${b.slug}&sort=created&limit=25`);
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card title="Research runs" pad={false}>
        {!runs ? <Spinner /> : !runs.length ? <Empty>No research runs yet.</Empty> : (
          <table className="table">
            <thead><tr><th>Run</th><th>Status</th><th>Retrieved</th><th>New</th><th>Qualified</th><th>Rejected</th></tr></thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td><Link className="link" to={`/runs/${r.id}`}>#{r.id}</Link><div className="text-[11px] text-slate-500">{dt(r.started_at)}</div></td>
                  <td><Badge tone={r.status === "succeeded" ? "good" : r.status === "partial" ? "warn" : r.status === "running" ? "info" : "bad"}>{r.status}</Badge></td>
                  <td className="num">{num(r.stats?.retrieved)}</td>
                  <td className="num">{num(r.stats?.new)}</td>
                  <td className="num">{num(r.stats?.qualified)}</td>
                  <td className="num">{num(r.stats?.rejected)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      <Card title="Latest discoveries" pad={false}>
        {recent ? <OpportunityTable items={recent.items} /> : <Spinner />}
      </Card>
    </div>
  );
}

function Pipeline({ b }: { b: any }) {
  const [sp, setSp] = useSearchParams();
  const stage = sp.get("stage") || "";
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const path = `/opportunities?business=${b.slug}${stage ? `&stage=${stage}` : "&open_only=true"}${q ? `&q=${encodeURIComponent(q)}` : ""}&limit=100&offset=${offset}`;
  const { data } = useApi<any>(path);
  return (
    <Card
      pad={false}
      title={`Pipeline${data ? ` · ${num(data.total)}` : ""}`}
      actions={
        <>
          <input className="input w-40 py-1 text-xs" placeholder="Filter…" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }} />
          <select className="input w-44 py-1 text-xs" value={stage} onChange={(e) => { setSp({ tab: "pipeline", ...(e.target.value ? { stage: e.target.value } : {}) }); setOffset(0); }}>
            <option value="">All open stages</option>
            {STAGES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </>
      }
    >
      {data ? <OpportunityTable items={data.items} /> : <Spinner />}
      {data && data.total > 100 && (
        <div className="flex justify-end gap-2 p-3">
          <button className="btn btn-sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 100))}>Prev</button>
          <span className="num self-center text-xs text-slate-500">{offset + 1}–{Math.min(offset + 100, data.total)} of {data.total}</span>
          <button className="btn btn-sm" disabled={offset + 100 >= data.total} onClick={() => setOffset(offset + 100)}>Next</button>
        </div>
      )}
    </Card>
  );
}

function Crm({ b }: { b: any }) {
  const { data, reload } = useApi<any[]>(`/contacts?business=${b.slug}`);
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ name: "", organization: "", role: "", email: "", phone: "", notes: "" });
  const [err, setErr] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await post("/contacts", { business: b.slug, ...Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v || null])), notes: f.notes });
      setOpen(false);
      setF({ name: "", organization: "", role: "", email: "", phone: "", notes: "" });
      reload();
    } catch (ex: any) { setErr(ex.message); }
  };
  return (
    <Card title="Contacts" pad={false} actions={<button className="btn btn-sm" onClick={() => setOpen(true)}>Add contact</button>}>
      <div className="px-4 pt-3"><Notice>Contacts marked <b>public record</b> were taken verbatim from official sources (e.g. permit applicants). The system never invents contact details.</Notice></div>
      {!data ? <Spinner /> : !data.length ? <Empty>No contacts yet.</Empty> : (
        <div className="overflow-x-auto">
          <table className="table">
            <thead><tr><th>Name</th><th>Role</th><th>Organization</th><th>Email / phone</th><th>Source</th><th></th></tr></thead>
            <tbody>
              {data.map((c) => (
                <tr key={c.id}>
                  <td className="font-medium">{c.name}{c.opportunity_id && <Link className="link ml-2 text-xs" to={`/o/${c.opportunity_id}`}>opp</Link>}</td>
                  <td className="text-slate-400">{c.role || "—"}</td>
                  <td className="text-slate-400">{c.organization || "—"}</td>
                  <td className="text-slate-400">{c.email || c.phone || "—"}</td>
                  <td><Badge tone={c.source === "public_record" ? "info" : "neutral"}>{c.source.replace("_", " ")}</Badge></td>
                  <td><button className="btn btn-sm" onClick={async () => { if (confirm("Delete contact?")) { await del(`/contacts/${c.id}`); reload(); } }}>Delete</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Modal open={open} onClose={() => setOpen(false)} title="Add contact">
        <form className="space-y-3" onSubmit={submit}>
          {(["name", "organization", "role", "email", "phone"] as const).map((k) => (
            <Field key={k} label={k[0].toUpperCase() + k.slice(1)}><input className="input" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></Field>
          ))}
          <Field label="Notes"><textarea className="input" rows={3} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
          <ErrorBox error={err} />
          <button className="btn btn-primary w-full" disabled={!f.name}>Save</button>
        </form>
      </Modal>
    </Card>
  );
}

export function TaskList({ business }: { business?: any }) {
  const [status, setStatus] = useState("open");
  const { data, reload } = useApi<any[]>(`/tasks?status=${status}${business ? `&business=${business.slug}` : ""}`);
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  return (
    <Card title="Tasks" pad={false} actions={
      <select className="input w-32 py-1 text-xs" value={status} onChange={(e) => setStatus(e.target.value)}>
        <option value="open">Open</option><option value="done">Done</option><option value="cancelled">Cancelled</option>
      </select>}>
      {business && (
        <form className="flex flex-wrap gap-2 border-b border-ink-700 p-3" onSubmit={async (e) => { e.preventDefault(); await post("/tasks", { business: business.slug, title, due_on: due || null }); setTitle(""); setDue(""); reload(); }}>
          <input className="input flex-1" placeholder="New task…" value={title} onChange={(e) => setTitle(e.target.value)} />
          <input className="input w-40" type="date" value={due} onChange={(e) => setDue(e.target.value)} />
          <button className="btn" disabled={!title}>Add</button>
        </form>
      )}
      {!data ? <Spinner /> : !data.length ? <Empty>No {status} tasks.</Empty> : (
        <ul>
          {data.map((t) => (
            <li key={t.id} className="flex items-start gap-3 border-b border-ink-800 px-4 py-2.5 last:border-0">
              <input type="checkbox" className="mt-1" checked={t.status === "done"} onChange={async () => { await patch(`/tasks/${t.id}`, { status: t.status === "done" ? "open" : "done" }); reload(); }} />
              <div className="min-w-0 flex-1">
                <div className="text-sm">{t.title} {t.priority === "high" && <Badge tone="warn">high</Badge>}</div>
                {t.detail && <pre className="mt-1 whitespace-pre-wrap font-sans text-xs text-slate-500">{t.detail}</pre>}
                <div className="mt-1 text-[11px] text-slate-600">
                  {t.created_by} · {day(t.created_at)} {t.due_on && <>· due {day(t.due_on)}</>} {t.opportunity_id && <Link className="link" to={`/o/${t.opportunity_id}`}>· opportunity</Link>}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Tasks({ b }: { b: any }) {
  return <TaskList business={b} />;
}

function BizFinance({ b }: { b: any }) {
  const { data, reload } = useApi<any[]>(`/finance/entries?business_id=${b.id}`);
  const [f, setF] = useState({ kind: "revenue", amount: "", occurred_on: new Date().toISOString().slice(0, 10), category: "general", description: "" });
  const [err, setErr] = useState<string | null>(null);
  const rev = (data || []).filter((x) => x.kind === "revenue").reduce((a, x) => a + x.amount, 0);
  const exp = (data || []).filter((x) => x.kind === "expense").reduce((a, x) => a + x.amount, 0);
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <Stat label="Actual revenue" value={money(rev)} tone="good" />
        <Stat label="Actual expenses" value={money(exp)} />
        <Stat label="Profit" value={money(rev - exp)} tone={rev - exp >= 0 ? "good" : "bad"} />
      </div>
      <Card title="Record actual revenue or expense">
        <form className="grid gap-2 sm:grid-cols-6" onSubmit={async (e) => {
          e.preventDefault(); setErr(null);
          try { await post("/finance/entries", { business_id: b.id, kind: f.kind, amount: Number(f.amount), occurred_on: f.occurred_on, category: f.category, description: f.description }); setF({ ...f, amount: "", description: "" }); reload(); } catch (ex: any) { setErr(ex.message); }
        }}>
          <select className="input" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}><option value="revenue">Revenue</option><option value="expense">Expense</option></select>
          <input className="input" type="number" step="0.01" min="0" placeholder="Amount" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} />
          <input className="input" type="date" value={f.occurred_on} onChange={(e) => setF({ ...f, occurred_on: e.target.value })} />
          <input className="input" placeholder="Category" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} />
          <input className="input" placeholder="Description" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
          <button className="btn btn-primary" disabled={!f.amount}>Add</button>
        </form>
        <div className="mt-2"><ErrorBox error={err} /></div>
        <p className="mt-2 text-xs text-slate-500">Only actual, realized amounts belong here. Pipeline estimates are tracked separately and never mixed with actuals.</p>
      </Card>
      <Card title="Entries" pad={false}>
        {!data ? <Spinner /> : !data.length ? <Empty>No financial entries.</Empty> : (
          <table className="table">
            <thead><tr><th>Date</th><th>Kind</th><th>Category</th><th>Description</th><th className="text-right">Amount</th><th></th></tr></thead>
            <tbody>{data.map((x) => (
              <tr key={x.id}><td>{day(x.occurred_on)}</td><td><Badge tone={x.kind === "revenue" ? "good" : "neutral"}>{x.kind}</Badge></td><td>{x.category}</td><td className="text-slate-400">{x.description}</td>
                <td className="num text-right">{money(x.amount, 2)}</td><td><button className="btn btn-sm" onClick={async () => { if (confirm("Delete entry?")) { await del(`/finance/entries/${x.id}`); reload(); } }}>✕</button></td></tr>
            ))}</tbody>
          </table>
        )}
      </Card>
    </div>
  );
}

function Recs({ b }: { b: any }) {
  const { data } = useApi<any>(`/opportunities?business=${b.slug}&stage=qualified&limit=25`);
  const { data: approvals } = useApi<any[]>(`/approvals?business=${b.slug}`);
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card title="Recommended next actions (qualified opportunities)" pad={false}>
        {!data ? <Spinner /> : !data.items.length ? <Empty>No qualified opportunities yet.</Empty> : (
          <ul>{data.items.map((o: any) => (
            <li key={o.id} className="border-b border-ink-800 px-4 py-3 last:border-0">
              <Link to={`/o/${o.id}`} className="text-sm font-medium hover:text-accent">{o.title}</Link>
              <div className="mt-1 text-xs text-slate-400">{o.recommended_action}</div>
              <div className="mt-1 text-[11px] text-slate-600">score {o.score.toFixed(0)} · confidence {Math.round(o.confidence * 100)}% · generated by deterministic Opportunity Analyst rules</div>
            </li>
          ))}</ul>
        )}
      </Card>
      <Card title="Awaiting your approval" pad={false}>
        {!approvals ? <Spinner /> : !approvals.length ? <Empty>Nothing pending.</Empty> : (
          <ul>{approvals.map((a) => (
            <li key={a.id} className="border-b border-ink-800 px-4 py-3 last:border-0">
              <Link to={`/approvals?open=${a.id}`} className="text-sm hover:text-accent">#{a.id} · {a.action_type.replace(/_/g, " ")}</Link>
              <div className="mt-1 text-xs text-slate-400">{a.proposed_action}</div>
            </li>
          ))}</ul>
        )}
      </Card>
    </div>
  );
}

function Reports({ b }: { b: any }) {
  const { data: briefs } = useApi<any[]>("/briefings?limit=10");
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card title="Exports">
        <div className="space-y-2 text-sm">
          <a className="btn" href={`/api/exports/opportunities.csv?business_id=${b.id}`}>Download opportunities (CSV)</a>
          <p className="text-xs text-slate-500">Includes source URLs, retrieval and verification dates. Expected values are labelled as estimates.</p>
        </div>
      </Card>
      <Card title="Portfolio briefings" pad={false}>
        {!briefs ? <Spinner /> : !briefs.length ? <Empty>No briefings yet.</Empty> : (
          <ul>{briefs.map((x) => (
            <li key={x.id} className="border-b border-ink-800 last:border-0"><Link className="block px-4 py-2 text-sm hover:bg-ink-850" to={`/briefings/${x.id}`}>{dt(x.created_at)} · {x.headline.discovered} discovered · {x.headline.approvals} approvals</Link></li>
          ))}</ul>
        )}
      </Card>
    </div>
  );
}

function Automation({ b, onChange }: { b: any; onChange: () => void }) {
  const { data: sources, reload } = useApi<any[]>(`/sources?business_id=${b.id}`);
  const [qt, setQt] = useState(String(b.qualify_threshold));
  const [rt, setRt] = useState(String(b.reject_threshold));
  const [rss, setRss] = useState({ name: "", url: "", keywords: "" });
  const [err, setErr] = useState<string | null>(null);
  return (
    <div className="space-y-4">
      <Card title="Automation controls">
        <div className="grid gap-4 sm:grid-cols-4">
          <KV k="Automated research" v={
            <button className={`btn btn-sm ${b.automation_enabled ? "btn-primary" : ""}`} onClick={async () => { await patch(`/businesses/${b.slug}`, { automation_enabled: !b.automation_enabled }); onChange(); }}>
              {b.automation_enabled ? "Enabled" : "Paused"}
            </button>} />
          <Field label="Qualification threshold (score)"><input className="input" type="number" value={qt} onChange={(e) => setQt(e.target.value)} /></Field>
          <Field label="Auto-reject below (score)"><input className="input" type="number" value={rt} onChange={(e) => setRt(e.target.value)} /></Field>
          <div className="flex items-end"><button className="btn" onClick={async () => { await patch(`/businesses/${b.slug}`, { qualify_threshold: Number(qt), reject_threshold: Number(rt) }); onChange(); }}>Save thresholds</button></div>
        </div>
      </Card>
      <Card title="Research sources" pad={false}>
        {!sources ? <Spinner /> : (
          <div className="overflow-x-auto"><table className="table">
            <thead><tr><th>Source</th><th>Status</th><th>Last success</th><th>Notes</th><th></th></tr></thead>
            <tbody>{sources.map((s) => (
              <tr key={s.id}>
                <td><div className="font-medium">{s.name}</div><div className="text-[11px] text-slate-500">{s.adapter} {s.official ? "· official publisher" : "· non-official"} · <ExtLink href={s.url}>link</ExtLink></div></td>
                <td><Badge tone={s.status === "active" ? "good" : s.status === "proposed" ? "info" : s.status === "disabled" ? "neutral" : "warn"}>{s.enabled ? s.status : "disabled"}</Badge></td>
                <td className="text-xs text-slate-400">{ago(s.last_success_at)}{s.last_error && <div className="text-danger">{s.last_error}</div>}</td>
                <td className="max-w-xs text-xs text-slate-500">{s.access_notes}</td>
                <td className="whitespace-nowrap">
                  <button className="btn btn-sm mr-1" onClick={async () => { await post(`/sources/${s.id}/run`); reload(); }}>Run now</button>
                  <button className="btn btn-sm" onClick={async () => { try { await patch(`/sources/${s.id}`, { enabled: !s.enabled }); reload(); } catch (ex: any) { alert(ex.message); } }}>{s.enabled ? "Disable" : "Enable"}</button>
                </td>
              </tr>
            ))}</tbody>
          </table></div>
        )}
      </Card>
      <Card title="Add an RSS / Atom feed (market intelligence)">
        <form className="grid gap-2 sm:grid-cols-4" onSubmit={async (e) => {
          e.preventDefault(); setErr(null);
          try { await post("/sources/rss", { business_id: b.id, name: rss.name, url: rss.url, keywords: rss.keywords.split(",").map((x) => x.trim()).filter(Boolean) }); setRss({ name: "", url: "", keywords: "" }); reload(); } catch (ex: any) { setErr(ex.message); }
        }}>
          <input className="input" placeholder="Name" value={rss.name} onChange={(e) => setRss({ ...rss, name: e.target.value })} />
          <input className="input" placeholder="https://…/feed.xml" value={rss.url} onChange={(e) => setRss({ ...rss, url: e.target.value })} />
          <input className="input" placeholder="keywords, comma separated" value={rss.keywords} onChange={(e) => setRss({ ...rss, keywords: e.target.value })} />
          <button className="btn" disabled={!rss.name || !rss.url}>Add feed</button>
        </form>
        <div className="mt-2"><ErrorBox error={err} /></div>
      </Card>
    </div>
  );
}
