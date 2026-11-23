import { Link } from "react-router-dom";
import { post } from "../api";
import OpportunityTable from "../components/OpportunityTable";
import { Card, EstimateTag, ErrorBox, PageHeader, Spinner, Stat, StatusDot } from "../components/ui";
import { ago, compact, money, usd } from "../format";
import { useApi } from "../hooks";

export default function Dashboard() {
  const { data: d, error, reload } = useApi<any>("/dashboard", { poll: 30000 });
  if (error) return <ErrorBox error={error} />;
  if (!d) return <Spinner />;
  const h = d.system_health;
  const ai = d.ai_costs;
  const aiPct = ai.monthly_budget_usd ? ai.month_usd / ai.monthly_budget_usd : 0;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Portfolio overview"
        sub={d.vault_unlocked ? "Including private ventures (vault unlocked)" : "Private ventures hidden (vault locked)"}
        actions={
          <>
            <button className="btn" onClick={async () => { await post("/jobs/research-cycle"); reload(); }}>
              Run research cycle now
            </button>
            {d.latest_briefing && (
              <Link className="btn btn-primary" to={`/briefings/${d.latest_briefing.id}`}>
                Latest briefing
              </Link>
            )}
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Active businesses" value={d.active_businesses} />
        <Stat label="New opportunities (7d)" value={d.new_opportunities_7d} sub={`${d.open_opportunities} open in total`} to="/pipeline" />
        <Stat label="Qualified pipeline" value={d.qualified_pipeline.count} sub={<span>{compact(d.qualified_pipeline.expected_value_estimate)} expected <EstimateTag /></span>} tone="good" to="/pipeline?stage=qualified" />
        <Stat label="Pending approvals" value={d.pending_approvals} tone={d.pending_approvals ? "warn" : undefined} to="/approvals" />
        <Stat label="Regulatory alerts" value={d.regulatory_alerts} tone={d.regulatory_alerts ? "warn" : undefined} to="/compliance" />
        <Stat label="Open tasks" value={d.open_tasks} />
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Jobs completed (24h)" value={d.research_jobs.completed_24h} sub={d.research_jobs.failed_24h ? `${d.research_jobs.failed_24h} failed` : "no failures"} tone={d.research_jobs.failed_24h ? "bad" : undefined} to="/system" />
        <Stat label="Jobs running" value={d.research_jobs.running} sub={`${d.research_jobs.queued} queued`} tone="info" to="/system" />
        <Stat label="Revenue (month)" value={money(d.financials.month.revenue)} sub="actual" to="/finance" />
        <Stat label="Expenses (month)" value={money(d.financials.month.expense)} sub="actual" to="/finance" />
        <Stat label="AI cost (month)" value={usd(ai.month_usd)} sub={`of ${money(ai.monthly_budget_usd)} budget`} tone={aiPct > 0.8 ? "warn" : undefined} to="/costs" />
        <Stat label="System health" value={<span className="flex items-center gap-2 text-base"><StatusDot ok={h.scheduler.alive} />{h.scheduler.alive ? "Workers OK" : "Scheduler down"}</span>} sub={h.sources_needing_attention ? `${h.sources_needing_attention} sources need attention` : "all sources OK"} to="/system" />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card title="Highest-ranked opportunities" className="xl:col-span-2" pad={false} actions={<Link to="/pipeline" className="link text-xs">All</Link>}>
          <OpportunityTable items={d.top_opportunities} showBusiness />
        </Card>
        <div className="space-y-4">
          <Card title="Businesses" pad={false}>
            <ul>
              {d.businesses.map((b: any) => (
                <li key={b.slug} className="border-b border-ink-800 last:border-0">
                  <Link to={`/b/${b.slug}`} className="flex items-center justify-between px-4 py-2 hover:bg-ink-850">
                    <span className="text-sm">
                      <span className="num mr-2 text-[10px] text-slate-600">{b.code}</span>
                      {b.name}
                    </span>
                    <span className="num text-xs text-slate-400">
                      {b.qualified} qual · {b.open} open
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
          <Card title="Latest briefing">
            {d.latest_briefing ? (
              <div className="text-sm">
                <div className="text-slate-400">Generated {ago(d.latest_briefing.created_at)}</div>
                <div className="mt-2 grid grid-cols-3 gap-2 text-center">
                  <div><div className="num text-lg">{d.latest_briefing.headline.discovered}</div><div className="text-[11px] text-slate-500">discovered</div></div>
                  <div><div className="num text-lg">{d.latest_briefing.headline.rejected}</div><div className="text-[11px] text-slate-500">rejected</div></div>
                  <div><div className="num text-lg text-warn">{d.latest_briefing.headline.approvals}</div><div className="text-[11px] text-slate-500">need approval</div></div>
                </div>
                <Link className="link mt-3 block text-xs" to={`/briefings/${d.latest_briefing.id}`}>Read briefing →</Link>
              </div>
            ) : (
              <p className="text-sm text-slate-500">No briefing yet. One is generated after each scheduled research cycle.</p>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
