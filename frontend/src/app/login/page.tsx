"use client";

/**
 * Login — laid out to match the ai-testing reference (pages/Login.tsx): one
 * centred 920px card, split into a brand panel and a form panel, on a radial
 * brand wash.
 *
 * Sign-in is email and password, as the reference is. Everything it has no
 * equivalent for has been removed rather than restyled: the inert "Need help?"
 * and language buttons, the SSO / create-account block with the two dialogs
 * those buttons were the only way to open, and the standard/LDAP mode switch
 * with its corporate-domain field. Remember me, show password and account
 * recovery survive, handlers untouched.
 *
 * Two endpoints are consequently unreachable from the UI: /users/register and
 * the LDAP token exchange. Both still exist server-side, and authApi.login /
 * authApi.ldapLogin still wrap them — this file simply no longer calls the
 * second, and a first account now has to be created against the API and
 * promoted in SQL (see the deployment notes).
 */

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  Eye,
  EyeOff,
} from "lucide-react";
import { authApi, getAccessToken, getAuthProfile, type TokenResponse } from "@/lib/api";

/** The reference's field treatment: 44px tall, 12px radius, brand focus ring. */
const FIELD =
  "h-11 w-full rounded-[12px] border border-app bg-white px-4 text-sm text-app-primary outline-none transition placeholder:text-app-muted focus:border-app-brand-600 focus:ring-2 focus:ring-app-brand-100";
const LABEL = "mb-1.5 block text-[13px] font-semibold text-app-primary";
/** Its primary button, down to the three-stop gradient and the lifted shadow. */
const PRIMARY_BUTTON =
  "flex h-11 w-full items-center justify-center gap-2 rounded-[12px] bg-[linear-gradient(180deg,#ff191f_0%,#d7141c_48%,#b91017_100%)] text-[14px] font-semibold text-white shadow-[0_8px_24px_rgba(183,25,32,0.22)] transition hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-app-brand-200 disabled:cursor-not-allowed disabled:opacity-70";
const SECONDARY_BUTTON =
  "flex h-11 w-full items-center justify-center gap-2 rounded-[12px] border border-app bg-white text-[13px] font-semibold text-app-primary transition hover:bg-app-surface-muted focus:outline-none focus:ring-2 focus:ring-app-brand-100";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [profile, setProfile] = useState<TokenResponse | null>(null);
  const [rememberMe, setRememberMe] = useState(true);
  const [recoveryModalOpen, setRecoveryModalOpen] = useState(false);
  const [copiedEmail, setCopiedEmail] = useState(false);

  useEffect(() => {
    if (getAccessToken()) {
      setProfile(getAuthProfile());
    }
    const savedEmail = localStorage.getItem("remember_email");
    if (savedEmail) {
      setEmail(savedEmail);
      setRememberMe(true);
    }
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await authApi.login(email.trim(), password);
      setProfile(response.data);
      if (rememberMe) {
        localStorage.setItem("remember_email", email.trim());
      } else {
        localStorage.removeItem("remember_email");
      }
      router.push("/dashboard");
    } catch {
      setError("Invalid email or password.");
    } finally {
      setLoading(false);
    }
  }

  function handleLogout() {
    authApi.logout();
    setProfile(null);
  }

  const brandMark = (
    <span className="flex h-10 w-10 items-center justify-center rounded-[12px] bg-[linear-gradient(135deg,#D52B31,#941216)] shadow-app-card">
      <Bot className="h-5 w-5 text-white" />
    </span>
  );

  return (
    <main className="flex min-h-screen items-center justify-center bg-[radial-gradient(ellipse_at_60%_40%,rgba(183,25,32,0.07),transparent_62%),radial-gradient(ellipse_at_10%_80%,rgba(253,235,236,0.6),transparent_50%)] px-4 py-10">
      <div className="w-full max-w-[920px] overflow-hidden rounded-[28px] bg-white shadow-[0_24px_72px_rgba(120,30,30,0.13)] lg:flex">

        {/* Left — brand panel. One centred stack rather than the reference's
            logo-top / copy-bottom split: the mark, the eyebrow, the wordmark
            and the strapline share an axis, so "eSMART" sits centred over
            "AI Automation Studio" instead of hanging off the left edge. */}
        <div className="relative hidden flex-col items-center justify-center bg-[linear-gradient(160deg,#4D0507_0%,#B71920_55%,#E8292E_100%)] p-10 text-center text-white lg:flex lg:w-[42%]">
          <div className="relative z-10 flex flex-col items-center">
            {brandMark}
            <p className="mb-3 mt-6 text-[11px] font-semibold uppercase tracking-[0.22em] text-white/60">
              Telecom QA Platform
            </p>
            <h1 className="text-[32px] font-bold leading-tight tracking-[-0.03em]">
              eSMART<br />AI Automation Studio
            </h1>
            <p className="mt-4 text-[14px] leading-7 text-white/70">
              Enterprise-grade AI Test Automation application for QA workflows.
            </p>
          </div>
          {/* decorative rings */}
          <div className="pointer-events-none absolute right-0 top-1/2 -translate-y-1/2 translate-x-1/2">
            <div className="h-[340px] w-[340px] rounded-full border border-white/[0.08]" />
            <div className="absolute inset-[44px] rounded-full border border-white/10" />
            <div className="absolute inset-[88px] rounded-full border border-white/[0.14]" />
          </div>
        </div>

        {/* Right — form panel */}
        <div className="flex flex-1 flex-col justify-center px-8 py-12 sm:px-12">
          {/* Brand mark for mobile, where the left panel is hidden */}
          <div className="mb-6 flex items-center gap-3 lg:hidden">
            {brandMark}
            <span className="text-[15px] font-bold tracking-[-0.02em] text-app-primary">eSMART - AI Automation Studio</span>
          </div>

          <div className="mb-8">
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.2em] text-app-brand-700">
              Welcome back
            </p>
            <h2 className="text-[26px] font-bold tracking-[-0.03em] text-app-primary">Sign in to continue</h2>
          </div>

          {error && (
            <div className="mb-5 flex items-start gap-2.5 rounded-[14px] border border-red-100 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className={LABEL}>Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className={FIELD}
                placeholder="name@company.com"
                autoComplete="email"
                required
              />
            </div>

            <div>
              <label className={LABEL}>Password</label>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className={`${FIELD} pr-11`}
                  placeholder="Enter your password"
                  autoComplete="current-password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-app-muted transition hover:text-app-secondary"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between">
              <label className="flex cursor-pointer items-center gap-2.5">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  className="h-4 w-4 cursor-pointer rounded border-app accent-app-brand-600"
                />
                <span className="text-[13px] font-medium text-app-secondary">Remember me</span>
              </label>
              <button
                type="button"
                onClick={() => setRecoveryModalOpen(true)}
                className="text-[13px] font-semibold text-app-brand-700 hover:underline"
              >
                Forgot password?
              </button>
            </div>

            <button type="submit" disabled={loading} className={`mt-1 ${PRIMARY_BUTTON}`}>
              {loading ? "Signing in…" : <>Sign In <ArrowRight className="h-4 w-4" /></>}
            </button>
          </form>

          {profile && (
            <div className="mt-6 rounded-[14px] border border-app bg-app-surface-muted p-4 text-[13px]">
              <div className="mb-2 flex items-center justify-between gap-3 border-b border-app pb-2">
                <span className="font-semibold text-app-primary">Active session token</span>
                <button type="button" onClick={handleLogout} className="font-semibold text-app-brand-700 hover:underline">
                  Sign out
                </button>
              </div>
              <div className="space-y-1 text-[12px] text-app-secondary">
                <p>Global role: <span className="font-mono uppercase text-app-primary">{profile.global_role ?? "n/a"}</span></p>
                <p>Project memberships: <span className="font-mono text-app-primary">{profile.project_memberships?.length ?? 0}</span></p>
              </div>
            </div>
          )}

        </div>
      </div>

      {/* Account Recovery */}
      {recoveryModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-app-primary/40 px-4 backdrop-blur-sm">
          <div className="fixed inset-0" onClick={() => setRecoveryModalOpen(false)} />
          <div className="relative z-10 w-full max-w-[440px] rounded-[20px] bg-white p-6 shadow-[0_24px_72px_rgba(120,30,30,0.16)]">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-[14px] border border-amber-100 bg-amber-50">
              <AlertTriangle className="h-6 w-6 text-amber-500" />
            </div>
            <h3 className="text-[18px] font-bold tracking-[-0.02em] text-app-primary">Enterprise account recovery</h3>
            <p className="mt-2.5 text-[13px] leading-6 text-app-secondary">
              Under corporate Active Directory (AD) and governance rules, user credentials are secure and
              centralized. Resets are managed by your platform administrators.
            </p>

            <div className="mt-5 space-y-3.5 rounded-[14px] border border-app bg-app-surface-muted p-4">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-app-muted">
                  Option A: contact admin
                </p>
                <p className="mt-1 text-[13px] leading-6 text-app-primary">
                  Contact the system admin or submit a support ticket to recover local database credentials.
                </p>
              </div>
              <div className="border-t border-app pt-3">
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-app-muted">
                  Option B: self-service portal
                </p>
                <p className="mt-1 text-[13px] leading-6 text-app-primary">
                  If your account is synced with LDAP/Okta/Azure AD, navigate to your enterprise portal to
                  reset your password.
                </p>
              </div>
            </div>

            <div className="mt-6 flex gap-3">
              <button
                type="button"
                onClick={() => {
                  navigator.clipboard.writeText("admin@stlc-platform.com");
                  setCopiedEmail(true);
                  setTimeout(() => setCopiedEmail(false), 2000);
                }}
                className={SECONDARY_BUTTON}
              >
                {copiedEmail ? "Copied!" : "Copy admin email"}
              </button>
              <button type="button" onClick={() => setRecoveryModalOpen(false)} className={PRIMARY_BUTTON}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}

    </main>
  );
}
