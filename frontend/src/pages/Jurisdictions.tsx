import { FormEvent, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { patch, post } from "../api";
import { Badge, Card, ErrorBox, ExtLink, Field, KV, Modal, Notice, PageHeader, Spinner } from "../components/ui";
import { ago, day } from "../format";
import { useApi } from "../hooks";

const TEXT_FIELDS: [string, string][] = [
  ["data_availability", "Data availability"],
  ["finder_registration", "Finder licensing / registration"],
  ["fee_restrictions", "Fee restrictions"],
  ["waiting_period", "Waiting periods"],
  ["claimant_authorization_rules", "Claimant authorization rules"],
  ["contract_requirements", "Contract requirements"],
  ["documentation_requirements", "Documentation requirements"],
  ["statutory_references", "Statutory references"],
  ["notes", "Notes"],
];

const tone = (s: string) => (s === "verified" ? "good" : s === "in_review" ? "info" : s === "needs_update" ? "bad" : "warn");

export default function Jurisdictions() {
  const { data, reload } = useApi<any[]>("/jurisdictions");
  const [sp, setSp] = useSearchParams();
  const [filter, setFilter] = useState("");
  const code = sp.get("code");
  const rows = useMemo(() => (data || []).filter((j) => !filter || `${j.code} ${j.name} ${j.agency_name}`.toLowerCase().includes(filter.toLowerCase())), [data, filter]);
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    (data || []).forEach((j) => { c[j.compliance_review_status] = (c[j.compliance_review_status] || 0) + 1; });
    return c;
  }, [data]);
  return (
    <div className="space-y-4">
      <PageHeader title="Jurisdiction intelligence — 50 states + DC" sub="Unclaimed-property programs and finder rules. Nothing is treated as legally cleared until you verify it with an official citation."
        actions={<button className="btn" onClick={async () => { await post("/jurisdictions/check-portals"); alert("Portal check queued."); }}>Check all portals now</button>} />
      <Notice tone="warn">
        Seeded agency names and URLs are a starting point only. Legal fields (licensing, fee caps, waiting periods, contracts) are blank until researched. Outreach approvals for asset recovery stay blocked in a jurisdiction until it is <b>verified</b> and <b>cleared</b>.
      </Notice>
      <div className="flex flex-wrap gap-2 text-xs">
        {Object.entries(counts).map(([k, v]) => <Badge key={k} tone={tone(k)}>{k.replace(/_/g, " ")}: {v}</Badge>)}
      </div>
      <Card pad={false} title="Registry" actions={<input className="input w-48 py-1 text-xs" placeholder="Filter…" value={filter} onChange={(e) => setFilter(e.target.value)} />}>
        {!data ? <Spinner /> : (
          <div className="overflow-x-auto"><table className="table">
            <thead><tr><th>Code</th><th>Agency</th><th>Rules</th><th>Operating</th><th className="hidden md:table-cell">Portal</th><th className="hidden lg:table-cell">Finder license</th><th className="hidden lg:table-cell">Last verified</th></tr></thead>
            <tbody>{rows.map((j) => (
              <tr key={j.code} className="cursor-pointer" onClick={() => setSp({ code: j.code })}>
                <td className="num font-semibold">{j.code}</td>
                <td><div>{j.name}</div><div className="text-xs text-slate-500">{j.agency_name}</div></td>
                <td><Badge tone={tone(j.compliance_review_status)}>{j.compliance_review_status.replace(/_/g, " ")}</Badge></td>
                <td><Badge tone={j.operating_status === "cleared" ? "good" : j.operating_status === "prohibited" ? "bad" : "neutral"}>{j.operating_status.replace(/_/g, " ")}</Badge></td>
                <td className="hidden text-xs md:table-cell"><Badge tone={j.portal_status === "reachable" ? "good" : j.portal_status === "unchecked" ? "neutral" : "warn"}>{j.portal_status}{j.portal_http_status ? ` ${j.portal_http_status}` : ""}</Badge><div className="text-slate-600">{ago(j.portal_last_checked_at)}</div></td>
                <td className="hidden lg:table-cell">{j.finder_license_required}</td>
                <td className="hidden text-xs lg:table-cell">{day(j.last_verified_at)}</td>
              </tr>
            ))}</tbody>
          </table></div>
        )}
      </Card>
      {code && <JurisdictionEditor code={code} onClose={() => { setSp({}); reload(); }} />}
    </div>
  );
}

function JurisdictionEditor({ code, onClose }: { code: string; onClose: () => void }) {
  const { data: j, setData } = useApi<any>(`/jurisdictions/${code}`);
  const [form, setForm] = useState<Record<string, any> | null>(null);
  const [cite, setCite] = useState({ title: "", url: "" });
  const [err, setErr] = useState<string | null>(null);
  const f = form || j;
  const save = async (e: FormEvent, extra: Record<string, any> = {}) => {
    e.preventDefault();
    setErr(null);
    try {
      const body: Record<string, any> = { ...extra };
      for (const [k] of TEXT_FIELDS) if (f[k] !== j[k]) body[k] = f[k];
      for (const k of ["finder_license_required", "bulk_data_available", "agency_url", "search_portal_url"]) if (f[k] !== j[k] && f[k]) body[k] = f[k];
      if (f.max_fee_percent !== j.max_fee_percent && f.max_fee_percent !== "" && f.max_fee_percent !== null) body.max_fee_percent = Number(f.max_fee_percent);
      if (cite.title && cite.url) body.add_citations = [cite];
      const r = await patch(`/jurisdictions/${code}`, body);
      setData(r); setForm(null); setCite({ title: "", url: "" });
    } catch (ex: any) { setErr(ex.message); }
  };
  return (
    <Modal open onClose={onClose} title={`${code} — jurisdiction rules`} wide>
      {!j ? <Spinner /> : (
        <form className="space-y-3" onSubmit={(e) => save(e)}>
          <div className="grid gap-x-8 sm:grid-cols-2">
            <KV k="Agency" v={j.agency_name} />
            <KV k="Agency site" v={<ExtLink href={j.agency_url}>open</ExtLink>} />
            <KV k="Search portal" v={<ExtLink href={j.search_portal_url}>open</ExtLink>} />
            <KV k="Portal status" v={`${j.portal_status} ${j.portal_http_status || ""} (${ago(j.portal_last_checked_at)})`} />
            <KV k="Rules status" v={<Badge tone={tone(j.compliance_review_status)}>{j.compliance_review_status}</Badge>} />
            <KV k="Verified" v={j.verified_by ? `${j.verified_by} · ${day(j.last_verified_at)}` : "never"} />
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Finder license required"><select className="input" value={f.finder_license_required} onChange={(e) => setForm({ ...f, finder_license_required: e.target.value })}><option>unknown</option><option>yes</option><option>no</option></select></Field>
            <Field label="Max finder fee %" hint="Only from statute/agency guidance"><input className="input" type="number" step="0.1" value={f.max_fee_percent ?? ""} onChange={(e) => setForm({ ...f, max_fee_percent: e.target.value })} /></Field>
            <Field label="Bulk data available"><select className="input" value={f.bulk_data_available} onChange={(e) => setForm({ ...f, bulk_data_available: e.target.value })}><option>unknown</option><option>yes</option><option>no</option><option>restricted</option></select></Field>
          </div>
          {TEXT_FIELDS.map(([k, label]) => (
            <Field key={k} label={label}><textarea className="input" rows={2} value={f[k] || ""} onChange={(e) => setForm({ ...f, [k]: e.target.value })} /></Field>
          ))}
          <div>
            <div className="h-label mb-1">Citations</div>
            <ul className="mb-2 space-y-1 text-xs">{(j.source_citations || []).map((c: any, i: number) => <li key={i}><ExtLink href={c.url}>{c.title}</ExtLink> {c.added_by && <span className="text-slate-500">· {c.added_by}</span>}</li>)}</ul>
            <div className="grid gap-2 sm:grid-cols-2">
              <input className="input" placeholder="Citation title (e.g. statute section)" value={cite.title} onChange={(e) => setCite({ ...cite, title: e.target.value })} />
              <input className="input" placeholder="https://official source" value={cite.url} onChange={(e) => setCite({ ...cite, url: e.target.value })} />
            </div>
          </div>
          <ErrorBox error={err} />
          <div className="flex flex-wrap gap-2">
            <button className="btn btn-primary">Save research</button>
            <button type="button" className="btn" onClick={(e) => save(e as any, { compliance_review_status: "in_review" })}>Mark in review</button>
            <button type="button" className="btn" onClick={(e) => { if (confirm("Mark rules VERIFIED? Only do this after checking the official statute/agency guidance.")) save(e as any, { compliance_review_status: "verified" }); }}>Mark verified</button>
            <button type="button" className="btn" onClick={(e) => save(e as any, { operating_status: "cleared" })}>Clear for operation</button>
            <button type="button" className="btn btn-danger" onClick={(e) => save(e as any, { operating_status: "prohibited" })}>Mark prohibited</button>
          </div>
        </form>
      )}
    </Modal>
  );
}
