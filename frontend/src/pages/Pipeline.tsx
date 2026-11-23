import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import OpportunityTable from "../components/OpportunityTable";
import { Card, EstimateTag, PageHeader, Spinner, STAGES } from "../components/ui";
import { compact, num } from "../format";
import { useApi } from "../hooks";

export default function Pipeline() {
  const [sp, setSp] = useSearchParams();
  const stage = sp.get("stage") || "";
  const [sort, setSort] = useState("score");
  const { data: summary } = useApi<any[]>("/pipeline/summary");
  const { data: biz } = useApi<any[]>("/businesses");
  const { data } = useApi<any>(`/opportunities?limit=200&sort=${sort}${stage ? `&stage=${stage}` : "&open_only=true"}`);
  const names = Object.fromEntries((biz || []).map((b) => [b.id, b.name]));
  return (
    <div className="space-y-4">
      <PageHeader title="Portfolio pipeline" sub="All visible businesses. Values in the funnel are reported source values and estimated expected values — not revenue." />
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6 xl:grid-cols-11">
        {(summary || []).map((s) => (
          <button key={s.stage} onClick={() => setSp(stage === s.stage ? {} : { stage: s.stage })}
            className={`card px-2 py-2 text-left transition-colors ${stage === s.stage ? "border-accent" : "hover:border-ink-500"}`}>
            <div className="text-[10px] uppercase tracking-wide text-slate-500">{s.label}</div>
            <div className="num text-lg">{num(s.count)}</div>
            <div className="num text-[10px] text-slate-500">{compact(s.expected_value_estimate_total)} exp.</div>
          </button>
        ))}
      </div>
      <Card pad={false} title={<span>{stage ? STAGES.find(([k]) => k === stage)?.[1] : "All open stages"} {data && `· ${num(data.total)}`} <EstimateTag /></span>}
        actions={<select className="input w-36 py-1 text-xs" value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="score">Sort: score</option><option value="created">Sort: newest</option><option value="value">Sort: reported value</option><option value="deadline">Sort: deadline</option>
        </select>}>
        {data ? <OpportunityTable items={data.items.map((o: any) => ({ ...o, business_name: names[o.business_id] }))} showBusiness /> : <Spinner />}
      </Card>
    </div>
  );
}
