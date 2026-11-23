import { FormEvent, useState } from "react";
import { patch, post } from "../api";
import { useAuth } from "../auth";
import { Badge, Card, ErrorBox, Field, Notice, PageHeader, Spinner } from "../components/ui";
import { useApi } from "../hooks";

export default function Settings() {
  return (
    <div className="space-y-4">
      <PageHeader title="Settings" />
      <div className="grid gap-4 xl:grid-cols-2">
        <AppSettings />
        <div className="space-y-4">
          <VaultPin />
          <Password />
          <Totp />
        </div>
      </div>
    </div>
  );
}

const LABELS: Record<string, string> = {
  monthly_operating_budget_usd: "Monthly operating budget target (USD)",
  ai_monthly_budget_usd: "AI monthly budget (USD)",
  ai_daily_budget_usd: "AI daily budget (USD)",
  ai_job_budget_usd: "AI budget per research job (USD)",
  ai_hard_limit: "Enforce hard AI limits",
  ai_warning_ratio: "Warn at fraction of budget",
  ai_max_requests_per_hour: "Max AI requests per hour",
  ai_briefing_summary_enabled: "AI summary on briefings",
  stale_after_days: "Mark leads stale after (days unseen)",
  research_max_records_per_run: "Max records per research run",
  auto_request_approvals: "Pipeline Manager files approval requests",
  max_auto_approvals_per_cycle: "Max auto approval requests per business per cycle",
  asset_recovery_assumed_fee_percent: "Asset recovery: ASSUMED finder fee % (when unverified)",
  asset_recovery_min_value_usd: "Asset recovery: minimum published value (USD)",
  asset_recovery_cost_per_claim_usd: "Asset recovery: estimated cost per claim (USD)",
  briefing_interval_hours: "Briefing interval (hours)",
};

function AppSettings() {
  const { data, reload } = useApi<any>("/settings");
  const [vals, setVals] = useState<Record<string, any> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  if (!data) return <Spinner />;
  const v = vals || data.values;
  const save = async () => {
    setErr(null); setOk(false);
    try {
      const changed = Object.fromEntries(Object.entries(v).filter(([k, x]) => JSON.stringify(x) !== JSON.stringify(data.values[k])));
      await patch("/settings", { values: changed });
      setVals(null); setOk(true); reload();
    } catch (ex: any) { setErr(ex.message); }
  };
  return (
    <Card title="Automation, cost control & research" actions={<button className="btn btn-sm btn-primary" onClick={save}>Save</button>}>
      <div className="space-y-3">
        <Notice>{data.secrets_note}</Notice>
        <div className="flex flex-wrap gap-2">{Object.entries(data.secrets_configured).map(([k, c]) => <Badge key={k} tone={c ? "good" : "neutral"}>{k}: {c ? "set" : "not set"}</Badge>)}</div>
        <div className="grid gap-3 sm:grid-cols-2">
          {Object.keys(LABELS).map((k) => typeof data.values[k] === "boolean" ? (
            <label key={k} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!v[k]} onChange={(e) => setVals({ ...v, [k]: e.target.checked })} />{LABELS[k]}</label>
          ) : (
            <Field key={k} label={LABELS[k]}><input className="input" type="number" step="any" min="0" value={v[k]} onChange={(e) => setVals({ ...v, [k]: e.target.value === "" ? "" : Number(e.target.value) })} /></Field>
          ))}
        </div>
        <Field label="AI model routing (JSON: role → provider/model)" hint="Roles: bulk_extraction (cheap, high-volume), analysis, briefing. Providers: anthropic, openai.">
          <textarea className="input num text-xs" rows={7} value={typeof v.ai_routes === "string" ? v.ai_routes : JSON.stringify(v.ai_routes, null, 2)}
            onChange={(e) => { try { setVals({ ...v, ai_routes: JSON.parse(e.target.value) }); } catch { setVals({ ...v, ai_routes: e.target.value }); } }} />
        </Field>
        <Field label="Pricing overrides (JSON: model → [input $/Mtok, output $/Mtok])" hint="Needed for OpenAI models; unknown models are costed conservatively.">
          <textarea className="input num text-xs" rows={3} value={typeof v.ai_pricing_overrides === "string" ? v.ai_pricing_overrides : JSON.stringify(v.ai_pricing_overrides, null, 2)}
            onChange={(e) => { try { setVals({ ...v, ai_pricing_overrides: JSON.parse(e.target.value) }); } catch { setVals({ ...v, ai_pricing_overrides: e.target.value }); } }} />
        </Field>
        <ErrorBox error={err} />
        {ok && <p className="text-sm text-accent">Saved.</p>}
      </div>
    </Card>
  );
}

function VaultPin() {
  const [f, setF] = useState({ current_pin: "", new_pin: "", password: "" });
  const [msg, setMsg] = useState<string | null>(null);
  const { refresh } = useAuth();
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try { await post("/vault/change-pin", f); setMsg("PIN changed. The vault has been locked in all sessions."); setF({ current_pin: "", new_pin: "", password: "" }); refresh(); } catch (ex: any) { setMsg(ex.message); }
  };
  return (
    <Card title="Private vault PIN">
      <form className="grid gap-2 sm:grid-cols-3" onSubmit={submit}>
        <input className="input" type="password" inputMode="numeric" placeholder="Current PIN" value={f.current_pin} onChange={(e) => setF({ ...f, current_pin: e.target.value })} />
        <input className="input" type="password" inputMode="numeric" placeholder="New PIN (4-8 digits)" value={f.new_pin} onChange={(e) => setF({ ...f, new_pin: e.target.value })} />
        <input className="input" type="password" placeholder="Account password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
        <button className="btn sm:col-span-3">Change PIN</button>
      </form>
      {msg && <p className="mt-2 text-sm text-slate-300">{msg}</p>}
      <p className="mt-2 text-xs text-slate-500">The PIN is an extra privacy barrier on top of your account login — not a substitute for it.</p>
    </Card>
  );
}

function Password() {
  const [f, setF] = useState({ current_password: "", new_password: "" });
  const [msg, setMsg] = useState<string | null>(null);
  return (
    <Card title="Account password">
      <form className="grid gap-2 sm:grid-cols-2" onSubmit={async (e) => { e.preventDefault(); try { await post("/auth/change-password", f); setMsg("Password changed; other sessions signed out."); setF({ current_password: "", new_password: "" }); } catch (ex: any) { setMsg(ex.message); } }}>
        <input className="input" type="password" placeholder="Current password" autoComplete="current-password" value={f.current_password} onChange={(e) => setF({ ...f, current_password: e.target.value })} />
        <input className="input" type="password" placeholder="New password" autoComplete="new-password" value={f.new_password} onChange={(e) => setF({ ...f, new_password: e.target.value })} />
        <button className="btn sm:col-span-2">Change password</button>
      </form>
      {msg && <p className="mt-2 text-sm text-slate-300">{msg}</p>}
    </Card>
  );
}

function Totp() {
  const { status, refresh } = useAuth();
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = useState("");
  const [pw, setPw] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const enabled = status?.user?.totp_enabled;
  return (
    <Card title="Two-factor authentication (authenticator app)">
      {enabled ? (
        <div className="space-y-2">
          <Badge tone="good">enabled</Badge>
          <div className="grid gap-2 sm:grid-cols-3">
            <input className="input" placeholder="Current code" value={code} onChange={(e) => setCode(e.target.value)} />
            <input className="input" type="password" placeholder="Password" value={pw} onChange={(e) => setPw(e.target.value)} />
            <button className="btn btn-danger" onClick={async () => { try { await post("/auth/totp/disable", { code, password: pw }); refresh(); } catch (ex: any) { setMsg(ex.message); } }}>Disable</button>
          </div>
        </div>
      ) : setup ? (
        <div className="space-y-2 text-sm">
          <p className="text-slate-400">Add this secret to your authenticator app (manual entry), then enter the 6-digit code:</p>
          <div className="num break-all rounded bg-ink-950 p-2 text-accent">{setup.secret}</div>
          <div className="flex gap-2"><input className="input" placeholder="123456" value={code} onChange={(e) => setCode(e.target.value)} />
            <button className="btn btn-primary" onClick={async () => { try { await post("/auth/totp/enable", { code }); setSetup(null); refresh(); } catch (ex: any) { setMsg(ex.message); } }}>Enable</button></div>
        </div>
      ) : (
        <button className="btn" onClick={async () => setSetup(await post("/auth/totp/setup"))}>Set up authenticator</button>
      )}
      {msg && <p className="mt-2 text-sm text-danger">{msg}</p>}
    </Card>
  );
}
