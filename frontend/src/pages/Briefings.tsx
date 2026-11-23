import { Link, useParams } from "react-router-dom";
import { post } from "../api";
import { Badge, Card, Empty, ErrorBox, ExtLink, PageHeader, Spinner } from "../components/ui";
import { dt, money } from "../format";
import { useApi } from "../hooks";

export default function Briefings() {
  const { data, reload } = useApi<any[]>("/briefings");
  return (
    <div className="space-y-4">
      <PageHeader title="Executive briefings" sub="Generated after each research cycle, strictly from stored research records."
        actions={<button className="btn" onClick={async () => { await post("/briefings/generate"); setTimeout(reload, 4000); }}>Generate now</button>} />
      <Card pad={false}>
        {!data ? <Spinner /> : !data.length ? <Empty>No briefings yet.</Empty> : (
          <ul>{data.map((b) => (
            <li key={b.id} className="border-b border-ink-800 last:border-0">
              <Link to={`/briefings/${b.id}`} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 hover:bg-ink-850">
                <span className="text-sm">Briefing #{b.id} · {dt(b.created_at)} {b.includes_private && <Badge tone="warn">includes private</Badge>}</span>
                <span className="num text-xs text-slate-400">{b.headline.discovered} discovered · {b.headline.rejected} rejected · {b.headline.approvals} approvals</span>
              </Link>
            </li>
          ))}</ul>
        )}
      </Card>
    </div>
  );
}

export function BriefingDetail() {
  const { id } = useParams();
  const { data: b, error } = useApi<any>(`/briefings/${id}`);
  if (error) return <ErrorBox error={error} />;
  if (!b) return <Spinner />;
  const c = b.content;
  return (
    <div className="space-y-4">
      <PageHeader title={`Executive briefing #${b.id}`} sub={`${dt(b.period_start)} → ${dt(b.period_end)} · ${b.generated_by}`} />
      {b.ai_summary && (
        <Card title={<span>Summary <Badge tone="ai">AI-written from the facts below</Badge></span>}>
          <pre className="whitespace-pre-wrap font-sans text-sm text-slate-300">{b.ai_summary}</pre>
        </Card>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="What did the system discover?">
          <p className="text-sm">{c.discovered.total} new opportunities.</p>
          <ul className="mt-2 text-sm text-slate-400">{Object.entries(c.discovered.by_business).map(([k, v]: any) => <li key={k}>{k}: <span className="num">{v}</span></li>)}</ul>
          <p className="mt-2 text-xs text-slate-500">Research runs: {c.research_runs.total} ({c.research_runs.succeeded} succeeded, {c.research_runs.partial} partial, {c.research_runs.failed} failed)</p>
        </Card>
        <Card title="What requires your approval?" pad={false}>
          {!c.approvals_required.length ? <Empty>Nothing pending.</Empty> : <ul>{c.approvals_required.map((a: any) => (
            <li key={a.id} className="border-b border-ink-800 px-4 py-2 text-sm last:border-0"><Link className="link" to={`/approvals?open=${a.id}`}>#{a.id}</Link> <span className="text-slate-500">{a.business}</span> — {a.proposed_action}</li>
          ))}</ul>}
        </Card>
      </div>
      <Card title="Which opportunities are strongest?" pad={false}>
        {!c.strongest.length ? <Empty>No qualified opportunities.</Empty> : <ul>{c.strongest.map((o: any) => (
          <li key={o.id} className="border-b border-ink-800 px-4 py-2.5 last:border-0">
            <Link className="text-sm font-medium hover:text-accent" to={`/o/${o.id}`}>{o.title}</Link>
            <div className="text-xs text-slate-500">{o.business} · score {o.score.toFixed(0)} · {o.stage} · reported {money(o.reported_value)} · expected (estimate) {money(o.expected_value)} · <ExtLink href={o.source_url}>source</ExtLink></div>
            <div className="text-xs text-slate-400">Next: {o.action}</div>
          </li>
        ))}</ul>}
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="What changed since the previous briefing?" pad={false}>
          {!c.changes.length ? <Empty>No tracked changes.</Empty> : <ul className="max-h-96 overflow-y-auto">{c.changes.map((x: any, i: number) => (
            <li key={i} className="border-b border-ink-800 px-4 py-2 text-xs last:border-0"><Link className="link" to={`/o/${x.opportunity_id}`}>{x.title}</Link> — {x.event} {x.detail}</li>
          ))}</ul>}
        </Card>
        <Card title={`Which leads were rejected? (${c.rejected.total})`} pad={false}>
          {!c.rejected.items.length ? <Empty>None.</Empty> : <ul className="max-h-96 overflow-y-auto">{c.rejected.items.map((x: any, i: number) => (
            <li key={i} className="border-b border-ink-800 px-4 py-2 text-xs last:border-0"><Link className="link" to={`/o/${x.opportunity_id}`}>{x.title}</Link><div className="text-slate-500">{x.reason}</div></li>
          ))}</ul>}
        </Card>
        <Card title="What legal or regulatory issues emerged?">
          <p className="text-sm">{c.regulatory.open_alerts} open alerts.</p>
          <ul className="mt-2 space-y-1 text-xs text-slate-400">{c.regulatory.new_alerts.map((a: any, i: number) => <li key={i}><Badge tone={a.severity === "warning" ? "warn" : "info"}>{a.severity}</Badge> {a.title}</li>)}</ul>
        </Card>
        <Card title="What research is planned next?">
          <ul className="space-y-1 text-sm text-slate-300">{c.planned_next.map((p: any, i: number) => <li key={i} className="flex justify-between gap-2"><span>{p.name}</span><span className="num text-xs text-slate-500">{dt(p.next_run_at)}</span></li>)}</ul>
          {c.research_runs.limitations.length > 0 && (
            <div className="mt-3"><div className="h-label mb-1">Limitations encountered</div>
              <ul className="space-y-1 text-xs text-warn">{c.research_runs.limitations.map((l: any, i: number) => <li key={i}>{l.source}: {(l.limitations || []).join("; ")}</li>)}</ul></div>
          )}
        </Card>
      </div>
    </div>
  );
}
