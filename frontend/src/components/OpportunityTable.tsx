import { Link } from "react-router-dom";
import { day, money } from "../format";
import { Badge, Empty, ScoreBar, StageBadge } from "./ui";

export type Opp = {
  id: number;
  title: string;
  entity_name: string | null;
  stage: string;
  score: number;
  confidence: number;
  reported_value: number | null;
  expected_value: number | null;
  original_source: string;
  jurisdiction_code: string | null;
  verification_status: string;
  last_verified_at: string | null;
  created_at: string;
  deadline: string | null;
  is_stale: boolean;
  business_name?: string;
  category?: string | null;
};

export default function OpportunityTable({ items, showBusiness }: { items: Opp[]; showBusiness?: boolean }) {
  if (!items.length) return <Empty>No opportunities yet. They appear automatically as research runs complete.</Empty>;
  return (
    <div className="overflow-x-auto">
      <table className="table">
        <thead>
          <tr>
            <th>Opportunity</th>
            {showBusiness && <th className="hidden md:table-cell">Business</th>}
            <th>Stage</th>
            <th>Score</th>
            <th className="text-right">Reported</th>
            <th className="hidden text-right sm:table-cell">Exp. value (est.)</th>
            <th className="hidden lg:table-cell">Source</th>
            <th className="hidden lg:table-cell">Verified</th>
          </tr>
        </thead>
        <tbody>
          {items.map((o) => (
            <tr key={o.id}>
              <td className="min-w-[14rem] max-w-[28rem]">
                <Link to={`/o/${o.id}`} title={o.title} className="line-clamp-2 font-medium text-slate-100 hover:text-accent">
                  {o.title}
                </Link>
                <div className="mt-0.5 flex flex-wrap gap-1 text-xs text-slate-500">
                  {o.jurisdiction_code && <Badge>{o.jurisdiction_code}</Badge>}
                  {o.is_stale && <Badge tone="warn">stale</Badge>}
                  {o.deadline && <span>due {day(o.deadline)}</span>}
                </div>
              </td>
              {showBusiness && <td className="hidden text-xs text-slate-400 md:table-cell">{o.business_name}</td>}
              <td>
                <span className="whitespace-nowrap"><StageBadge stage={o.stage} /></span>
              </td>
              <td>
                <ScoreBar score={o.score} />
              </td>
              <td className="num text-right">{money(o.reported_value)}</td>
              <td className={`num hidden text-right sm:table-cell ${o.expected_value && o.expected_value > 0 ? "text-warn" : "text-slate-500"}`}>{money(o.expected_value)}</td>
              <td className="hidden max-w-[14rem] truncate text-xs text-slate-400 lg:table-cell">{o.original_source}</td>
              <td className="hidden text-xs text-slate-400 lg:table-cell">{day(o.last_verified_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
