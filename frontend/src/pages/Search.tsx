import { Link, useSearchParams } from "react-router-dom";
import OpportunityTable from "../components/OpportunityTable";
import { Card, Empty, PageHeader, Spinner } from "../components/ui";
import { useApi } from "../hooks";

export default function Search() {
  const [sp] = useSearchParams();
  const q = sp.get("q") || "";
  const { data } = useApi<any>(q.length >= 2 ? `/search?q=${encodeURIComponent(q)}` : null);
  return (
    <div className="space-y-4">
      <PageHeader title={`Search: “${q}”`} sub="Results respect the private vault: locked ventures are never searched." />
      {!data ? <Spinner /> : (
        <>
          <Card title={`Opportunities (${data.opportunities.length})`} pad={false}><OpportunityTable items={data.opportunities} /></Card>
          <div className="grid gap-4 md:grid-cols-3">
            <Card title="Businesses" pad={false}>{!data.businesses.length ? <Empty>None.</Empty> : <ul>{data.businesses.map((b: any) => <li key={b.id} className="px-4 py-2 text-sm"><Link className="link" to={`/b/${b.slug}`}>{b.name}</Link></li>)}</ul>}</Card>
            <Card title="Contacts" pad={false}>{!data.contacts.length ? <Empty>None.</Empty> : <ul>{data.contacts.map((c: any) => <li key={c.id} className="px-4 py-2 text-sm">{c.name} <span className="text-xs text-slate-500">{c.role}</span></li>)}</ul>}</Card>
            <Card title="Tasks" pad={false}>{!data.tasks.length ? <Empty>None.</Empty> : <ul>{data.tasks.map((t: any) => <li key={t.id} className="px-4 py-2 text-sm">{t.title}</li>)}</ul>}</Card>
          </div>
        </>
      )}
    </div>
  );
}
