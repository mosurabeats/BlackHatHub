import { FormEvent, ReactNode, useEffect, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { post } from "../api";
import { useAuth } from "../auth";
import { useApi } from "../hooks";
import { Modal } from "./ui";

type Biz = { slug: string; name: string; code: string; is_private: boolean };

function NavItem({ to, children, badge }: { to: string; children: ReactNode; badge?: number }) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      className={({ isActive }) =>
        `flex items-center justify-between rounded-md px-2.5 py-1.5 text-sm transition-colors ${isActive ? "bg-ink-700 text-slate-100" : "text-slate-400 hover:bg-ink-800 hover:text-slate-200"}`
      }
    >
      <span className="truncate">{children}</span>
      {!!badge && <span className="num ml-2 rounded bg-warn/20 px-1.5 text-[11px] text-warn">{badge}</span>}
    </NavLink>
  );
}

export function VaultUnlock({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { refresh } = useAuth();
  const [pin, setPin] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await post("/vault/unlock", { pin });
      setPin("");
      await refresh();
      onClose();
    } catch (ex: any) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal open={open} onClose={onClose} title="Unlock private ventures">
      <form onSubmit={submit} className="space-y-3">
        <p className="text-sm text-slate-400">The vault locks automatically after 15 minutes of inactivity, on logout, or when you lock it.</p>
        <input
          className="input num text-center text-2xl tracking-[0.5em]"
          type="password"
          inputMode="numeric"
          autoComplete="off"
          autoFocus
          maxLength={8}
          value={pin}
          onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
          placeholder="••••"
          aria-label="Vault PIN"
        />
        {err && <p className="text-sm text-danger">{err}</p>}
        <button className="btn btn-primary w-full" disabled={busy || pin.length < 4}>
          Unlock
        </button>
      </form>
    </Modal>
  );
}

export default function Layout({ children }: { children: ReactNode }) {
  const { status, lockVault, logout } = useAuth();
  const unlocked = !!status?.vault.unlocked;
  const { data: businesses } = useApi<Biz[]>("/businesses");
  const { data: dash } = useApi<any>("/dashboard", { poll: 60000 });
  const [menu, setMenu] = useState(false);
  const [unlock, setUnlock] = useState(false);
  const [q, setQ] = useState("");
  const nav = useNavigate();
  const loc = useLocation();
  useEffect(() => setMenu(false), [loc.pathname]);

  const pub = (businesses || []).filter((b) => !b.is_private);
  const priv = (businesses || []).filter((b) => b.is_private);

  const sidebar = (
    <nav className="flex h-full flex-col gap-4 overflow-y-auto p-3">
      <Link to="/" className="flex items-center gap-2 px-2 pt-1">
        <img src="/favicon.svg" className="h-7 w-7" alt="" />
        <div>
          <div className="text-sm font-semibold text-slate-100">Executive Hub</div>
          <div className="text-[10px] uppercase tracking-wider text-slate-500">Portfolio OS</div>
        </div>
      </Link>
      <div className="space-y-0.5">
        <NavItem to="/">Dashboard</NavItem>
        <NavItem to="/approvals" badge={dash?.pending_approvals}>
          Approvals
        </NavItem>
        <NavItem to="/briefings">Briefings</NavItem>
        <NavItem to="/pipeline">Pipeline</NavItem>
        <NavItem to="/compliance" badge={dash?.regulatory_alerts}>
          Compliance
        </NavItem>
      </div>
      <div>
        <div className="h-label px-2.5 pb-1">Businesses</div>
        <div className="space-y-0.5">
          {pub.map((b) => (
            <NavItem key={b.slug} to={`/b/${b.slug}`}>
              <span className="num mr-1.5 text-[10px] text-slate-600">{b.code}</span>
              {b.name}
            </NavItem>
          ))}
        </div>
      </div>
      <div>
        <div className="flex items-center justify-between px-2.5 pb-1">
          <span className="h-label">Private ventures</span>
          {unlocked ? (
            <button className="text-[11px] text-warn hover:underline" onClick={() => lockVault()}>
              Lock
            </button>
          ) : (
            <button className="text-[11px] text-slate-400 hover:text-slate-200" onClick={() => setUnlock(true)}>
              Unlock
            </button>
          )}
        </div>
        {unlocked ? (
          <div className="space-y-0.5">
            {priv.map((b) => (
              <NavItem key={b.slug} to={`/b/${b.slug}`}>
                <span className="num mr-1.5 text-[10px] text-slate-600">{b.code}</span>
                {b.name}
              </NavItem>
            ))}
          </div>
        ) : (
          <div className="px-2.5 text-xs text-slate-600">Locked</div>
        )}
      </div>
      <div>
        <div className="h-label px-2.5 pb-1">Intelligence</div>
        <div className="space-y-0.5">
          <NavItem to="/jurisdictions">Jurisdictions (51)</NavItem>
          <NavItem to="/research">Research &amp; Sources</NavItem>
          <NavItem to="/finance">Finance</NavItem>
          <NavItem to="/costs">AI Costs</NavItem>
        </div>
      </div>
      <div className="mt-auto space-y-0.5 border-t border-ink-700 pt-3">
        <NavItem to="/system">System</NavItem>
        <NavItem to="/settings">Settings</NavItem>
        <button className="w-full rounded-md px-2.5 py-1.5 text-left text-sm text-slate-500 hover:bg-ink-800 hover:text-slate-300" onClick={() => logout()}>
          Sign out {status?.user?.username}
        </button>
      </div>
    </nav>
  );

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 border-r border-ink-700 bg-ink-900 lg:block">{sidebar}</aside>
      {menu && (
        <div className="fixed inset-0 z-40 bg-black/60 lg:hidden" onClick={() => setMenu(false)}>
          <aside className="h-full w-72 border-r border-ink-700 bg-ink-900" onClick={(e) => e.stopPropagation()}>
            {sidebar}
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center gap-2 border-b border-ink-700 bg-ink-950/90 px-3 py-2 backdrop-blur pt-[max(0.5rem,env(safe-area-inset-top))]">
          <button className="btn btn-sm lg:hidden" onClick={() => setMenu(true)} aria-label="Menu">
            ☰
          </button>
          <form
            className="min-w-0 flex-1"
            onSubmit={(e) => {
              e.preventDefault();
              if (q.trim().length >= 2) nav(`/search?q=${encodeURIComponent(q.trim())}`);
            }}
          >
            <input className="input max-w-md py-1.5" placeholder="Search opportunities, contacts, tasks…" value={q} onChange={(e) => setQ(e.target.value)} />
          </form>
          {unlocked ? (
            <button className="btn btn-sm border-warn/40 text-warn" onClick={() => lockVault()} title="Private vault is unlocked">
              🔓 <span className="hidden sm:inline">Vault unlocked</span>
            </button>
          ) : (
            <button className="btn btn-sm" onClick={() => setUnlock(true)} title="Unlock private ventures">
              🔒 <span className="hidden sm:inline">Vault</span>
            </button>
          )}
        </header>
        {status?.vault_initial_pin && (
          <div className="border-b border-warn/30 bg-warn/10 px-4 py-1.5 text-xs text-warn">
            The private vault still uses the initial PIN. <Link className="underline" to="/settings">Change it in Settings.</Link>
          </div>
        )}
        <main className="mx-auto w-full max-w-[1500px] flex-1 px-4 py-5 pb-[max(1.25rem,env(safe-area-inset-bottom))]">{children}</main>
      </div>
      <VaultUnlock open={unlock} onClose={() => setUnlock(false)} />
    </div>
  );
}
