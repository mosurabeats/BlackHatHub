import { useState } from "react";
import { Link } from "react-router-dom";
import { post } from "../api";
import BarChart from "../components/BarChart";
import { Badge, Card, EstimateTag, ErrorBox, PageHeader, Spinner, Stat } from "../components/ui";
import { compact, money, usd } from "../format";
import { useApi } from "../hooks";

export default function Finance() {
  const { data: d, reload } = useApi<any>("/finance/summary");
  const [fc, setFc] = useState({ business_id: "", period: new Date().toISOString().slice(0, 7), revenue: "", expenses: "", notes: "" });
  const [err, setErr] = useState<string | null>(null);
  if (!d) return <Spinner />;
  const p = d.portfolio_actual;
  return (
    <div className="space-y-4">
      <PageHeader title="Financial performance" sub="Actuals, forecasts and pipeline estimates are kept strictly separate."
        actions={<a className="btn" href="/api/exports/financials.csv">Export actuals (CSV)</a>} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Actual revenue (all time)" value={money(p.revenue)} tone="good" />
        <Stat label="Actual expenses" value={money(p.expenses)} />
        <Stat label="Actual profit" value={money(p.profit)} tone={p.profit >= 0 ? "good" : "bad"} />
        <Stat label="AI spend this month" value={usd(d.operating_budget.ai_month_to_date_usd)} sub={`operating target ${money(d.operating_budget.monthly_target_usd)}/mo`} to="/costs" />
      </div>
      <Card title="Monthly actuals (last 12 months)">
        <BarChart labels={d.monthly_actuals.map((m: any) => m.month.slice(2))} format={(v) => compact(v)}
          series={[{ name: "Revenue (actual)", values: d.monthly_actuals.map((m: any) => m.revenue) }, { name: "Expenses (actual)", values: d.monthly_actuals.map((m: any) => m.expense) }]} />
      </Card>
      <Card title="Profitability by business" pad={false}>
        <div className="overflow-x-auto"><table className="table">
          <thead><tr><th>Business</th><th className="text-right">Revenue</th><th className="text-right">Expenses</th><th className="text-right">Profit</th><th className="text-right">AI cost</th><th className="text-right">Forecast rev.</th><th className="text-right">Pipeline exp. value <EstimateTag /></th></tr></thead>
          <tbody>{d.by_business.map((b: any) => (
            <tr key={b.business_id}>
              <td><Link className="hover:text-accent" to={`/b/${b.slug}?tab=finance`}>{b.name}</Link> {b.is_private && <Badge tone="warn">private</Badge>}</td>
              <td className="num text-right">{money(b.actual.revenue)}</td>
              <td className="num text-right">{money(b.actual.expenses)}</td>
              <td className={`num text-right ${b.actual.profit < 0 ? "text-danger" : ""}`}>{money(b.actual.profit)}</td>
              <td className="num text-right">{usd(b.ai_cost_attributed)}</td>
              <td className="num text-right text-slate-400">{money(b.forecast_future.revenue)}</td>
              <td className="num text-right text-warn">{money(b.pipeline_expected_value_estimate)}</td>
            </tr>
          ))}</tbody>
        </table></div>
        <p className="px-4 py-2 text-[11px] text-slate-500">{d.labels.pipeline}. {d.labels.forecast}.</p>
      </Card>
      <Card title="Add / update a forecast (owner estimate)">
        <form className="grid gap-2 sm:grid-cols-6" onSubmit={async (e) => {
          e.preventDefault(); setErr(null);
          try { await post("/finance/forecasts", { business_id: Number(fc.business_id), period: fc.period, revenue: Number(fc.revenue || 0), expenses: Number(fc.expenses || 0), notes: fc.notes }); reload(); setFc({ ...fc, revenue: "", expenses: "", notes: "" }); } catch (ex: any) { setErr(ex.message); }
        }}>
          <select className="input sm:col-span-2" value={fc.business_id} onChange={(e) => setFc({ ...fc, business_id: e.target.value })}>
            <option value="">Business…</option>{d.by_business.map((b: any) => <option key={b.business_id} value={b.business_id}>{b.name}</option>)}
          </select>
          <input className="input" type="month" value={fc.period} onChange={(e) => setFc({ ...fc, period: e.target.value })} />
          <input className="input" type="number" min="0" placeholder="Revenue" value={fc.revenue} onChange={(e) => setFc({ ...fc, revenue: e.target.value })} />
          <input className="input" type="number" min="0" placeholder="Expenses" value={fc.expenses} onChange={(e) => setFc({ ...fc, expenses: e.target.value })} />
          <button className="btn" disabled={!fc.business_id}>Save forecast</button>
        </form>
        <div className="mt-2"><ErrorBox error={err} /></div>
      </Card>
    </div>
  );
}
