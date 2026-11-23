import { ReactNode, useEffect } from "react";
import { Link } from "react-router-dom";

export function Card({ title, actions, children, className = "", pad = true }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; pad?: boolean }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-2 border-b border-ink-700 px-4 py-2.5">
          <h2 className="h-label">{title}</h2>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className={pad ? "card-pad" : ""}>{children}</div>
    </section>
  );
}

export function Stat({ label, value, sub, tone, to }: { label: string; value: ReactNode; sub?: ReactNode; tone?: "good" | "warn" | "bad" | "info"; to?: string }) {
  const color = tone === "good" ? "text-accent" : tone === "warn" ? "text-warn" : tone === "bad" ? "text-danger" : tone === "info" ? "text-info" : "text-slate-100";
  const body = (
    <div className="card h-full px-4 py-3 transition-colors hover:border-ink-600">
      <div className="h-label">{label}</div>
      <div className={`num mt-1 text-2xl font-semibold ${color}`}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-slate-500">{sub}</div>}
    </div>
  );
  return to ? <Link to={to}>{body}</Link> : body;
}

const STAGE_COLORS: Record<string, string> = {
  discovered: "bg-slate-700/50 text-slate-300",
  researching: "bg-info/15 text-info",
  verified: "bg-cyan-500/15 text-cyan-300",
  qualified: "bg-accent/15 text-accent",
  awaiting_approval: "bg-warn/15 text-warn",
  outreach_approved: "bg-violet-500/15 text-violet-300",
  contacted: "bg-indigo-500/15 text-indigo-300",
  negotiating: "bg-fuchsia-500/15 text-fuchsia-300",
  active: "bg-emerald-500/20 text-emerald-300",
  won: "bg-emerald-500/30 text-emerald-200",
  lost: "bg-ink-700 text-slate-500",
};

export const STAGES: [string, string][] = [
  ["discovered", "Discovered"],
  ["researching", "Researching"],
  ["verified", "Verified"],
  ["qualified", "Qualified"],
  ["awaiting_approval", "Awaiting Approval"],
  ["outreach_approved", "Outreach Approved"],
  ["contacted", "Contacted"],
  ["negotiating", "Negotiating"],
  ["active", "Active"],
  ["won", "Won"],
  ["lost", "Lost / Rejected"],
];
export const stageLabel = (s: string) => STAGES.find(([k]) => k === s)?.[1] ?? s;

export function StageBadge({ stage }: { stage: string }) {
  return <span className={`tag ${STAGE_COLORS[stage] || "bg-ink-700"}`}>{stageLabel(stage)}</span>;
}

export function Badge({ children, tone = "neutral", title }: { children: ReactNode; tone?: "neutral" | "good" | "warn" | "bad" | "info" | "ai"; title?: string }) {
  const c = {
    neutral: "bg-ink-700 text-slate-300",
    good: "bg-accent/15 text-accent",
    warn: "bg-warn/15 text-warn",
    bad: "bg-danger/15 text-danger",
    info: "bg-info/15 text-info",
    ai: "bg-violet-500/15 text-violet-300",
  }[tone];
  return (
    <span title={title} className={`tag ${c}`}>
      {children}
    </span>
  );
}

export function EstimateTag() {
  return (
    <Badge tone="warn" title="Speculative estimate. Never counted as revenue.">
      ESTIMATE
    </Badge>
  );
}

export function ScoreBar({ score }: { score: number }) {
  const c = score >= 70 ? "bg-accent" : score >= 50 ? "bg-info" : score >= 30 ? "bg-warn" : "bg-slate-600";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-14 overflow-hidden rounded bg-ink-700">
        <div className={`h-full ${c}`} style={{ width: `${Math.min(100, Math.max(0, score))}%` }} />
      </div>
      <span className="num text-xs text-slate-300">{score.toFixed(0)}</span>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="px-4 py-8 text-center text-sm text-slate-500">{children}</div>;
}

export function Spinner() {
  return <div className="px-4 py-8 text-center text-sm text-slate-500">Loading…</div>;
}

export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return <div className="rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">{error}</div>;
}

export function Notice({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "warn" }) {
  const c = tone === "warn" ? "border-warn/40 bg-warn/10 text-warn" : "border-info/30 bg-info/10 text-info";
  return <div className={`rounded-md border px-3 py-2 text-sm ${c}`}>{children}</div>;
}

export function Modal({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: string; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    if (open) window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-0 sm:items-center sm:p-4" onClick={onClose}>
      <div className={`card max-h-[92vh] w-full overflow-y-auto ${wide ? "sm:max-w-3xl" : "sm:max-w-lg"}`} onClick={(e) => e.stopPropagation()}>
        <header className="flex items-center justify-between border-b border-ink-700 px-4 py-3">
          <h3 className="text-sm font-semibold">{title}</h3>
          <button className="btn btn-sm" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}

export function Tabs({ tabs, active, onChange }: { tabs: [string, string][]; active: string; onChange: (k: string) => void }) {
  return (
    <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
      <div className="flex min-w-max gap-1 border-b border-ink-700">
        {tabs.map(([k, label]) => (
          <button
            key={k}
            onClick={() => onChange(k)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm transition-colors ${active === k ? "border-accent text-slate-100" : "border-transparent text-slate-500 hover:text-slate-300"}`}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function KV({ k, v }: { k: ReactNode; v: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-b border-ink-800 py-1.5 text-sm last:border-0">
      <span className="text-slate-500">{k}</span>
      <span className="text-right text-slate-200">{v}</span>
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-slate-400">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-slate-500">{hint}</span>}
    </label>
  );
}

export function PageHeader({ title, sub, actions }: { title: ReactNode; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-slate-100">{title}</h1>
        {sub && <p className="mt-0.5 text-sm text-slate-500">{sub}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function ExtLink({ href, children }: { href?: string | null; children?: ReactNode }) {
  if (!href) return <span className="text-slate-600">—</span>;
  return (
    <a className="link break-all" href={href} target="_blank" rel="noopener noreferrer nofollow">
      {children || href}
    </a>
  );
}

export function StatusDot({ ok, warn }: { ok: boolean; warn?: boolean }) {
  return <span className={`inline-block h-2 w-2 rounded-full ${ok ? "bg-accent" : warn ? "bg-warn" : "bg-danger"}`} />;
}
