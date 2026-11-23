import { useState } from "react";
import { patch } from "../api";
import BarChart from "../components/BarChart";
import { Card, Empty, Field, Notice, PageHeader, Spinner, Stat } from "../components/ui";
import { money, num, usd } from "../format";
import { useApi } from "../hooks";

export default function Costs() {
  const { data: d, reload } = useApi<any>("/costs/summary", { poll: 60000 });
  const [b, setB] = useState<Record<string, string> | null>(null);
  if (!d) return <Spinner />;
  const s = d.spend;
  const form = b || { ai_daily_budget_usd: String(s.daily_budget_usd), ai_monthly_budget_usd: String(s.monthly_budget_usd) };
  return (
    <div className="space-y-4">
      <PageHeader title="AI operating costs" sub={d.label} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Today" value={usd(s.today_usd)} sub={`daily budget ${money(s.daily_budget_usd, 2)}`} tone={s.today_usd > s.daily_budget_usd * s.warning_ratio ? "warn" : undefined} />
        <Stat label="This month" value={usd(s.month_usd)} sub={`monthly budget ${money(s.monthly_budget_usd, 2)}`} tone={s.month_usd > s.monthly_budget_usd * s.warning_ratio ? "warn" : undefined} />
        <Stat label="Blocked by budget" value={d.blocked_by_budget_this_month} sub="requests this month" />
        <Stat label="Cache hits" value={d.cache_hits_this_month} sub="requests served free" />
      </div>
      {!s.hard_limit && <Notice tone="warn">Hard limits are OFF: requests over budget will proceed with a warning.</Notice>}
      <Card title="Daily AI spend (this month)">
        {d.daily.length ? <BarChart labels={d.daily.map((x: any) => x.date.slice(5))} series={[{ name: "AI cost", values: d.daily.map((x: any) => x.cost_usd) }]} format={(v) => `$${v.toFixed(2)}`} height={150} />
          : <Empty>No AI usage this month. Research runs on deterministic parsers; AI is used only for unstructured sources and briefing summaries when an API key is configured.</Empty>}
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="By model" pad={false}>
          {!d.by_model.length ? <Empty>None.</Empty> : <table className="table"><thead><tr><th>Model</th><th className="text-right">Requests</th><th className="text-right">Tokens in/out</th><th className="text-right">Cost</th></tr></thead>
            <tbody>{d.by_model.map((m: any) => <tr key={m.model}><td>{m.provider}/{m.model}</td><td className="num text-right">{m.requests}</td><td className="num text-right">{num(m.input_tokens)} / {num(m.output_tokens)}</td><td className="num text-right">{usd(m.cost_usd)}</td></tr>)}</tbody></table>}
        </Card>
        <Card title="By agent" pad={false}>
          {!d.by_agent.length ? <Empty>None.</Empty> : <table className="table"><thead><tr><th>Agent</th><th className="text-right">Requests</th><th className="text-right">Cost</th></tr></thead>
            <tbody>{d.by_agent.map((m: any) => <tr key={m.agent}><td>{m.agent}</td><td className="num text-right">{m.requests}</td><td className="num text-right">{usd(m.cost_usd)}</td></tr>)}</tbody></table>}
        </Card>
      </div>
      <Card title="Budgets & model routing">
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Daily AI budget (USD)"><input className="input" type="number" step="0.5" min="0" value={form.ai_daily_budget_usd} onChange={(e) => setB({ ...form, ai_daily_budget_usd: e.target.value })} /></Field>
          <Field label="Monthly AI budget (USD)"><input className="input" type="number" step="1" min="0" value={form.ai_monthly_budget_usd} onChange={(e) => setB({ ...form, ai_monthly_budget_usd: e.target.value })} /></Field>
          <div className="flex items-end"><button className="btn btn-primary" onClick={async () => { await patch("/settings", { values: { ai_daily_budget_usd: Number(form.ai_daily_budget_usd), ai_monthly_budget_usd: Number(form.ai_monthly_budget_usd) } }); setB(null); reload(); }}>Save budgets</button></div>
        </div>
        <div className="mt-4 space-y-1 text-sm">
          {Object.entries(d.routes).map(([role, r]: any) => <div key={role} className="flex justify-between border-b border-ink-800 py-1"><span className="text-slate-400">{role.replace(/_/g, " ")}</span><span className="num">{r.provider} / {r.model}</span></div>)}
          <p className="pt-1 text-xs text-slate-500">Edit routes, per-job budget and request limits in Settings.</p>
        </div>
      </Card>
    </div>
  );
}
