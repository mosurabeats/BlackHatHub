import { FormEvent, useState } from "react";
import { post } from "../api";
import { useAuth } from "../auth";

export default function Login() {
  const { status, refresh } = useAuth();
  const setup = !!status?.setup_required;
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [totp, setTotp] = useState("");
  const [needTotp, setNeedTotp] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (setup && password !== confirm) return setErr("Passwords do not match");
    setBusy(true);
    try {
      if (setup) await post("/auth/setup", { username, password });
      else await post("/auth/login", { username, password, totp: totp || undefined });
      await refresh();
    } catch (ex: any) {
      if (/Authenticator code required/.test(ex.message)) setNeedTotp(true);
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4 p-6">
        <div className="flex items-center gap-3">
          <img src="/favicon.svg" className="h-9 w-9" alt="" />
          <div>
            <h1 className="text-lg font-semibold">Executive Hub</h1>
            <p className="text-xs text-slate-500">{setup ? "Create the owner account" : "Sign in"}</p>
          </div>
        </div>
        {setup && (
          <p className="rounded-md border border-info/30 bg-info/10 p-2 text-xs text-info">
            First run: choose a username and a strong password (12+ characters, mixed character types). You can enable an authenticator app afterwards in Settings.
          </p>
        )}
        <input className="input" placeholder="Username" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
        <input className="input" type="password" placeholder="Password" autoComplete={setup ? "new-password" : "current-password"} value={password} onChange={(e) => setPassword(e.target.value)} />
        {setup && <input className="input" type="password" placeholder="Confirm password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />}
        {needTotp && <input className="input num tracking-widest" inputMode="numeric" placeholder="Authenticator code" value={totp} onChange={(e) => setTotp(e.target.value)} />}
        {err && <p className="text-sm text-danger">{err}</p>}
        <button className="btn btn-primary w-full" disabled={busy || !username || !password}>
          {setup ? "Create account" : "Sign in"}
        </button>
        <p className="text-center text-[11px] text-slate-600">Private system. Access is limited to the local network and Tailscale.</p>
      </form>
    </div>
  );
}
