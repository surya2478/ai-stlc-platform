"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  Bot,
  Eye,
  EyeOff,
  Lock,
  Mail,
  ShieldCheck,
  Cpu,
  Radio,
  Globe,
  ChevronDown,
  Shield,
  ArrowRight,
  Fingerprint,
  UserPlus,
} from "lucide-react";
import { authApi, getAccessToken, getAuthProfile, type TokenResponse } from "@/lib/api";

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
  const [ssoModalOpen, setSsoModalOpen] = useState(false);
  const [signupModalOpen, setSignupModalOpen] = useState(false);
  const [copiedEmail, setCopiedEmail] = useState(false);
  const [ssoNotice, setSsoNotice] = useState("");
  const [signupName, setSignupName] = useState("");
  const [signupEmail, setSignupEmail] = useState("");
  const [signupPassword, setSignupPassword] = useState("");
  const [signupLoading, setSignupLoading] = useState(false);
  const [signupError, setSignupError] = useState("");
  const [signupSuccess, setSignupSuccess] = useState("");
  const [loginMode, setLoginMode] = useState<"standard" | "ldap">("standard");
  const [domain, setDomain] = useState("CORP.NET");

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
      const response = loginMode === "ldap"
        ? await authApi.ldapLogin(email.trim(), password, domain)
        : await authApi.login(email.trim(), password);
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

  async function handleSignup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSignupLoading(true);
    setSignupError("");
    setSignupSuccess("");
    try {
      await authApi.register({
        email: signupEmail.trim().toLowerCase(),
        full_name: signupName.trim(),
        password: signupPassword,
      });
      setEmail(signupEmail.trim().toLowerCase());
      setPassword("");
      setSignupSuccess("Account created. You can sign in now.");
      setSignupPassword("");
    } catch (signupErr: any) {
      const payload = signupErr?.response?.data;
      const detail = payload?.detail;
      if (typeof payload === "string" && payload.trim()) {
        setSignupError(payload);
      } else if (typeof detail === "string") {
        setSignupError(detail);
      } else if (Array.isArray(detail) && detail.length > 0) {
        const messages = detail
          .map((item) => (typeof item?.msg === "string" ? item.msg : null))
          .filter(Boolean);
        setSignupError(messages.length > 0 ? messages.join(" ") : "Could not create your account right now.");
      } else if (signupErr?.response?.status === 429) {
        setSignupError("Too many sign-up attempts from this network. Please wait about an hour and try again.");
      } else {
        setSignupError("Could not create your account right now.");
      }
      return;
    } finally {
      setSignupLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#f8fafc] text-slate-900 select-none overflow-hidden relative">
      <div className="grid min-h-screen lg:grid-cols-[1.1fr_0.9fr]">
        
        {/* Left Column: Platform info & network illustration */}
        <section className="relative flex flex-col justify-between bg-gradient-to-br from-white via-[#f0f5ff] to-[#e6efff] px-8 py-8 lg:px-16 lg:py-12 overflow-hidden">
          
          {/* Curvy background separator SVG */}
          <svg className="absolute top-0 right-0 h-full w-32 translate-x-[99%] pointer-events-none overflow-visible z-10 hidden lg:block" viewBox="0 0 100 1000" preserveAspectRatio="none">
            <path d="M 0 0 C 80 250, -40 750, 0 1000 L 0 1000 L 0 0 Z" fill="#e6efff" className="fill-[#e6efff]" />
            <path d="M 0 0 C 80 250, -40 750, 0 1000" fill="none" stroke="url(#cyanGrad)" strokeWidth="3" />
            <defs>
              <linearGradient id="cyanGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#06b6d4" />
                <stop offset="50%" stopColor="#06b6d4" />
                <stop offset="100%" stopColor="#3b82f6" />
              </linearGradient>
            </defs>
          </svg>

          {/* Background globe network image */}
          <div className="absolute right-0 bottom-0 w-[80%] h-[60%] opacity-40 pointer-events-none select-none z-0">
            <img src="/login_bg.png" alt="Telecom Network Globe" className="object-contain object-bottom right-0 bottom-0 w-full h-full" />
          </div>

          <div className="relative z-20 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-cyan-500 to-indigo-600 shadow-md">
              <Bot className="h-5.5 w-5.5 text-white" />
            </div>
            <div>
              <h2 className="text-base font-black text-slate-800 leading-none">AI STLC Platform</h2>
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mt-1.5">Telecom QA Command Center</p>
            </div>
          </div>

          <div className="relative z-20 max-w-md my-auto py-12">
            <h1 className="text-3xl lg:text-[40px] font-black text-slate-900 tracking-tight leading-[1.15]">
              Secure access to your <br />
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-cyan-500">AI-powered QA</span> <br />
              command center
            </h1>
            <p className="text-xs lg:text-sm text-slate-500 font-semibold leading-relaxed mt-4">
              Accelerate release readiness with intelligent automation, full traceability, and telecom-grade quality engineering.
            </p>

            <div className="space-y-6 mt-12">
              {/* Enterprise Secure */}
              <div className="flex items-start gap-4">
                <div className="h-8 w-8 shrink-0 flex items-center justify-center rounded-lg bg-emerald-50 border border-emerald-100 text-emerald-500 shadow-sm">
                  <ShieldCheck className="h-4.5 w-4.5" />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider">Enterprise Secure</h4>
                  <p className="text-xs text-slate-400 font-semibold leading-relaxed mt-1">
                    STLC-grade security with role-based access and audit-ready governance.
                  </p>
                </div>
              </div>

              {/* AI-Powered Automation */}
              <div className="flex items-start gap-4">
                <div className="h-8 w-8 shrink-0 flex items-center justify-center rounded-lg bg-emerald-50 border border-emerald-100 text-emerald-500 shadow-sm">
                  <Cpu className="h-4.5 w-4.5" />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider">AI-Powered Automation</h4>
                  <p className="text-xs text-slate-400 font-semibold leading-relaxed mt-1">
                    Intelligent test generation, execution, and self-healing at scale.
                  </p>
                </div>
              </div>

              {/* Telecom-Grade Quality */}
              <div className="flex items-start gap-4">
                <div className="h-8 w-8 shrink-0 flex items-center justify-center rounded-lg bg-emerald-50 border border-emerald-100 text-emerald-500 shadow-sm">
                  <Radio className="h-4.5 w-4.5" />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider">Telecom-Grade Quality</h4>
                  <p className="text-xs text-slate-400 font-semibold leading-relaxed mt-1">
                    Built for complex networks, services, and customer experience.
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div className="relative z-20 flex items-center gap-1.5 text-[10px] font-bold text-slate-400 uppercase tracking-wider">
            <ShieldCheck className="h-4 w-4 text-emerald-500" />
            <span>Trusted by telecom enterprises worldwide</span>
          </div>
        </section>

        {/* Right Column: Sign in card & utilities */}
        <section className="flex flex-col justify-between p-8 lg:p-12 bg-[#f8fafc]">
          
          {/* Help & Language */}
          <div className="flex items-center justify-end gap-3 text-xs font-bold text-slate-400 self-end">
            <button className="hover:text-slate-650 transition-colors">Need help?</button>
            <span className="text-slate-200">|</span>
            <button className="flex items-center gap-1 text-slate-600 hover:text-slate-850 transition-colors">
              <Globe className="h-3.5 w-3.5" />
              English
              <ChevronDown className="h-3 w-3" />
            </button>
          </div>

          {/* Login Card */}
          <div className="w-full max-w-[420px] mx-auto bg-white rounded-[24px] border border-slate-100 p-8 lg:p-10 shadow-lg shadow-slate-100/50 flex flex-col justify-between my-auto">
            <div>
              <div className="h-16 w-16 mx-auto rounded-full bg-slate-50 border border-slate-100 flex items-center justify-center text-slate-450">
                <div className="h-10 w-10 rounded-full bg-gradient-to-tr from-slate-50 to-slate-100 flex items-center justify-center">
                  <Lock className="h-4.5 w-4.5 text-slate-400" />
                </div>
              </div>

              <h2 className="text-xl font-black text-slate-800 text-center tracking-tight mt-5">Sign in</h2>
              <p className="text-[11px] text-slate-450 font-semibold text-center mt-2 leading-relaxed">
                Use your corporate account to access <br /> the AI STLC Command Center.
              </p>

              {/* Login Mode Tabs */}
              <div className="flex rounded-xl bg-slate-100 p-1 mt-6">
                <button
                  type="button"
                  onClick={() => setLoginMode("standard")}
                  className={`flex-1 py-2 text-center text-xs font-bold rounded-lg transition-colors ${
                    loginMode === "standard"
                      ? "bg-white text-slate-800 shadow-sm"
                      : "text-slate-500 hover:text-slate-850"
                  }`}
                >
                  Standard Login
                </button>
                <button
                  type="button"
                  onClick={() => setLoginMode("ldap")}
                  className={`flex-1 py-2 text-center text-xs font-bold rounded-lg transition-colors ${
                    loginMode === "ldap"
                      ? "bg-white text-slate-800 shadow-sm"
                      : "text-slate-500 hover:text-slate-850"
                  }`}
                >
                  LDAP / NT Login
                </button>
              </div>

              {/* Form */}
              <form onSubmit={handleSubmit} className="space-y-6 mt-6">
                <div>
                  <label className="block text-[10px] font-bold text-slate-450 uppercase tracking-wider mb-2">
                    {loginMode === "ldap" ? "NT Username" : "Email"}
                  </label>
                  <div className="flex items-center gap-2.5 rounded-xl border border-slate-200 px-3.5 py-3 bg-white focus-within:border-[#1b59f8] focus-within:ring-1 focus-within:ring-[#1b59f8]/10 transition-all">
                    <Mail className="h-4.5 w-4.5 text-slate-400 shrink-0" />
                    <input
                      type={loginMode === "ldap" ? "text" : "email"}
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="w-full bg-transparent text-sm text-slate-850 font-semibold outline-none placeholder:text-slate-300"
                      placeholder={loginMode === "ldap" ? "first.last" : "name@company.com"}
                      required
                    />
                  </div>
                </div>

                {loginMode === "ldap" && (
                  <div>
                    <label className="block text-[10px] font-bold text-slate-450 uppercase tracking-wider mb-2">Corporate Domain</label>
                    <div className="flex items-center gap-2.5 rounded-xl border border-slate-200 px-3.5 py-3 bg-white focus-within:border-[#1b59f8] focus-within:ring-1 focus-within:ring-[#1b59f8]/10 transition-all">
                      <Globe className="h-4.5 w-4.5 text-slate-400 shrink-0" />
                      <input
                        type="text"
                        value={domain}
                        onChange={(e) => setDomain(e.target.value)}
                        className="w-full bg-transparent text-sm text-slate-850 font-semibold outline-none placeholder:text-slate-300"
                        placeholder="CORP.NET"
                        required
                      />
                    </div>
                  </div>
                )}

                <div>
                  <label className="block text-[10px] font-bold text-slate-450 uppercase tracking-wider mb-2">Password</label>
                  <div className="flex items-center gap-2.5 rounded-xl border border-slate-200 px-3.5 py-3 bg-white focus-within:border-[#1b59f8] focus-within:ring-1 focus-within:ring-[#1b59f8]/10 transition-all">
                    <Lock className="h-4.5 w-4.5 text-slate-400 shrink-0" />
                    <input
                      type={showPassword ? "text" : "password"}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="w-full bg-transparent text-sm text-slate-850 font-semibold outline-none placeholder:text-slate-350"
                      placeholder="••••••••••••"
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="text-slate-400 hover:text-slate-650 transition-colors animate-fade-in"
                    >
                      {showPassword ? <EyeOff className="h-4.5 w-4.5" /> : <Eye className="h-4.5 w-4.5" />}
                    </button>
                  </div>
                </div>

                {/* Remember me & Forgot password */}
                <div className="flex items-center justify-between pt-1 select-none">
                  <label className="flex items-center gap-2.5 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={rememberMe}
                      onChange={(e) => setRememberMe(e.target.checked)}
                      className="h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500 cursor-pointer accent-emerald-600"
                    />
                    <span className="text-xs font-bold text-slate-500">Remember me</span>
                  </label>
                  <button
                    type="button"
                    onClick={() => setRecoveryModalOpen(true)}
                    className="text-xs font-bold text-[#1b59f8] hover:underline"
                  >
                    Forgot password?
                  </button>
                </div>

                {/* Error message */}
                {error && (
                  <div className="flex items-start gap-2.5 rounded-xl border border-rose-100 bg-rose-50/50 px-3.5 py-2.5 text-xs font-semibold text-rose-600">
                    <AlertTriangle className="h-4.5 w-4.5 shrink-0 mt-0.5" />
                    <span>{error}</span>
                  </div>
                )}

                {/* Submit button */}
                <button
                  type="submit"
                  disabled={loading}
                  className="w-full bg-[#0a1835] hover:bg-[#12244a] text-white rounded-xl py-3.5 text-sm font-bold flex items-center justify-center gap-2 transition-colors disabled:opacity-70 disabled:cursor-not-allowed shadow-sm mt-2"
                >
                  {loading ? "Signing in..." : <>Sign in <ArrowRight className="h-4 w-4" /></>}
                </button>
              </form>

              {/* Separator */}
              <div className="relative flex items-center justify-center my-5">
                <div className="absolute inset-0 flex items-center"><span className="w-full border-t border-slate-100" /></div>
                <span className="relative bg-white px-3 text-[10px] font-extrabold text-slate-400 uppercase tracking-wider">or</span>
              </div>

              {/* SSO */}
              <button
                type="button"
                onClick={() => setSsoModalOpen(true)}
                className="w-full bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 rounded-xl py-2.5 text-xs font-bold flex items-center justify-center gap-2 transition-colors"
              >
                <Fingerprint className="h-4 w-4 text-slate-400" />
                Sign in with SSO
              </button>

              <button
                type="button"
                onClick={() => {
                  setSignupModalOpen(true);
                  setSignupError("");
                  setSignupSuccess("");
                  setSignupName("");
                  setSignupEmail(email.trim());
                  setSignupPassword("");
                }}
                className="w-full bg-slate-50 hover:bg-slate-100 border border-slate-200 text-slate-700 rounded-xl py-2.5 text-xs font-bold flex items-center justify-center gap-2 transition-colors mt-3"
              >
                <UserPlus className="h-4 w-4 text-slate-400" />
                Create account
              </button>
            </div>

            {/* Existing token profile */}
            {profile && (
              <div className="mt-5 rounded-xl border border-slate-100 bg-slate-50 p-3.5 text-xs font-semibold">
                <div className="flex items-center justify-between gap-3 border-b border-slate-200/50 pb-2 mb-2">
                  <span className="text-slate-700">Active Session Token</span>
                  <button type="button" onClick={handleLogout} className="text-red-500 hover:underline">
                    Sign out
                  </button>
                </div>
                <div className="space-y-1 text-[10px] text-slate-500">
                  <p>Global Role: <span className="text-slate-700 uppercase font-mono">{profile.global_role ?? "n/a"}</span></p>
                  <p>Project Memberships: <span className="text-slate-700 font-mono">{profile.project_memberships?.length ?? 0}</span></p>
                </div>
              </div>
            )}

            {/* Bottom Security */}
            <div className="mt-6 text-center flex items-center justify-center gap-1.5 text-[9px] font-bold text-slate-400">
              <Shield className="h-3.5 w-3.5 text-slate-300" />
              <span>Secure STLC access • Encrypted in transit • Enterprise grade</span>
            </div>
          </div>

          {/* Footer spacing */}
          <div className="h-6" />
        </section>
      </div>

      {/* Account Recovery Dialog Modal */}
      {recoveryModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div 
            className="fixed inset-0" 
            onClick={() => setRecoveryModalOpen(false)}
          />
          <div className="relative bg-white rounded-3xl border border-slate-100 p-6 shadow-xl w-full max-w-[420px] mx-4 animate-scale-up z-10">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-50 border border-amber-100 text-amber-505 mb-4">
              <AlertTriangle className="h-6 w-6 text-amber-500" />
            </div>
            <h3 className="text-base font-black text-slate-800 tracking-tight">Enterprise Account Recovery</h3>
            <p className="text-xs text-slate-500 font-semibold leading-relaxed mt-2.5">
              Under corporate Active Directory (AD) and governance rules, user credentials are secure and centralized. Resets are managed by your platform administrators.
            </p>
            
            <div className="mt-5 space-y-3.5 bg-slate-50 rounded-2xl border border-slate-100 p-4">
              <div>
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Option A: Contact Admin</p>
                <p className="text-xs font-semibold text-slate-700 mt-1 leading-normal">
                  Contact the system admin or submit a support ticket to recover local database credentials.
                </p>
              </div>
              <div className="border-t border-slate-200/50 pt-3">
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Option B: Self-Service Portal</p>
                <p className="text-xs font-semibold text-slate-700 mt-1 leading-normal">
                  If your account is synced with LDAP/Okta/Azure AD, navigate to your enterprise portal to reset your password.
                </p>
              </div>
            </div>

            <div className="flex gap-2.5 mt-6">
              <button
                type="button"
                onClick={() => {
                  navigator.clipboard.writeText("admin@stlc-platform.com");
                  setCopiedEmail(true);
                  setTimeout(() => setCopiedEmail(false), 2000);
                }}
                className="flex-1 bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 rounded-xl py-2.5 text-xs font-bold flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
              >
                {copiedEmail ? "Copied!" : "Copy Admin Email"}
              </button>
              <button
                type="button"
                onClick={() => setRecoveryModalOpen(false)}
                className="flex-1 bg-[#0a1835] hover:bg-[#12244a] text-white rounded-xl py-2.5 text-xs font-bold transition-colors cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {signupModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div
            className="fixed inset-0"
            onClick={() => setSignupModalOpen(false)}
          />
          <div className="relative bg-white rounded-3xl border border-slate-100 p-6 shadow-xl w-full max-w-[420px] mx-4 animate-scale-up z-10">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-50 border border-emerald-100 text-emerald-500 mb-4">
              <UserPlus className="h-6 w-6" />
            </div>
            <h3 className="text-base font-black text-slate-800 tracking-tight">Create your account</h3>
            <p className="text-xs text-slate-500 font-semibold leading-relaxed mt-2.5">
              Create the first platform account for your production workspace.
            </p>

            <form onSubmit={handleSignup} className="space-y-4 mt-5">
              <div>
                <label className="block text-[10px] font-bold text-slate-450 uppercase tracking-wider mb-2">Full name</label>
                <input
                  type="text"
                  value={signupName}
                  onChange={(e) => setSignupName(e.target.value)}
                  className="w-full rounded-xl border border-slate-200 px-3.5 py-3 text-sm font-semibold text-slate-850 outline-none focus:border-[#1b59f8] focus:ring-1 focus:ring-[#1b59f8]/10"
                  placeholder="Surya"
                  required
                />
              </div>

              <div>
                <label className="block text-[10px] font-bold text-slate-450 uppercase tracking-wider mb-2">Email</label>
                <input
                  type="email"
                  value={signupEmail}
                  onChange={(e) => setSignupEmail(e.target.value)}
                  className="w-full rounded-xl border border-slate-200 px-3.5 py-3 text-sm font-semibold text-slate-850 outline-none focus:border-[#1b59f8] focus:ring-1 focus:ring-[#1b59f8]/10"
                  placeholder="surya@gmail.com"
                  required
                />
              </div>

              <div>
                <label className="block text-[10px] font-bold text-slate-450 uppercase tracking-wider mb-2">Password</label>
                <input
                  type="password"
                  value={signupPassword}
                  onChange={(e) => setSignupPassword(e.target.value)}
                  className="w-full rounded-xl border border-slate-200 px-3.5 py-3 text-sm font-semibold text-slate-850 outline-none focus:border-[#1b59f8] focus:ring-1 focus:ring-[#1b59f8]/10"
                  placeholder="At least 12 chars with upper, lower, number, special"
                  required
                />
                <p className="mt-2 text-[11px] font-semibold text-slate-400">
                  Use 12+ characters with uppercase, lowercase, number, and special character.
                </p>
              </div>

              {signupError && (
                <div className="rounded-xl border border-rose-100 bg-rose-50/50 px-3.5 py-2.5 text-xs font-semibold text-rose-600">
                  {signupError}
                </div>
              )}

              {signupSuccess && (
                <div className="rounded-xl border border-emerald-100 bg-emerald-50 px-3.5 py-2.5 text-xs font-semibold text-emerald-700">
                  {signupSuccess}
                </div>
              )}

              <div className="flex gap-2.5 pt-2">
                <button
                  type="button"
                  onClick={() => setSignupModalOpen(false)}
                  className="flex-1 border border-slate-200 text-slate-700 hover:bg-slate-50 rounded-xl py-2.5 text-xs font-bold transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={signupLoading}
                  className="flex-1 bg-[#0a1835] hover:bg-[#12244a] text-white rounded-xl py-2.5 text-xs font-bold transition-colors disabled:opacity-70"
                >
                  {signupLoading ? "Creating..." : "Create account"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* SSO & LDAP Authentication Modal */}
      {ssoModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div 
            className="fixed inset-0" 
            onClick={() => setSsoModalOpen(false)}
          />
          <div className="relative bg-white rounded-3xl border border-slate-100 p-6 shadow-xl w-full max-w-[420px] mx-4 animate-scale-up z-10">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-50 border border-blue-100 text-blue-505 mb-4">
              <Fingerprint className="h-6 w-6 text-[#1b59f8]" />
            </div>
            <h3 className="text-base font-black text-slate-800 tracking-tight">Identity Provider Sign In</h3>
            
            {!ssoNotice ? (
              <>
                <p className="text-xs text-slate-500 font-semibold leading-relaxed mt-2.5">
                  Access the STLC command center using your corporate single sign-on (SSO) or active directory credentials.
                </p>

                <div className="mt-5 space-y-2">
                  {[
                    { name: "Okta Tenant Authentication", provider: "okta" },
                    { name: "Microsoft Azure Active Directory", provider: "azure" },
                    { name: "Ping Identity Federated SSO", provider: "ping" }
                  ].map((idp) => (
                    <button
                      key={idp.provider}
                      type="button"
                      onClick={() => {
                        setSsoNotice(`SSO connection to ${idp.name} is currently not configured. Please contact your IT administrator.`);
                      }}
                      className="w-full bg-slate-50 hover:bg-slate-100 border border-slate-200/60 rounded-xl px-4 py-3 text-xs font-bold text-slate-700 flex items-center justify-between transition-colors group cursor-pointer"
                    >
                      <span>{idp.name}</span>
                      <ArrowRight className="h-4 w-4 text-slate-400 group-hover:translate-x-0.5 transition-transform" />
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <>
                <div className="mt-4 p-4 rounded-2xl bg-amber-50 border border-amber-100 text-amber-900 text-xs font-semibold leading-relaxed">
                  <p className="font-bold text-amber-800">SSO Integration Coming Soon</p>
                  <p className="mt-1">{ssoNotice}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setSsoNotice("")}
                  className="w-full bg-slate-50 hover:bg-slate-100 border border-slate-200 text-slate-750 rounded-xl py-2.5 text-xs font-bold transition-colors mt-5 cursor-pointer"
                >
                  Back to Providers
                </button>
              </>
            )}

            <button
              type="button"
              onClick={() => {
                setSsoModalOpen(false);
                setSsoNotice("");
              }}
              className="w-full border border-slate-200 text-slate-750 hover:bg-slate-50 rounded-xl py-2.5 text-xs font-bold transition-colors mt-4 cursor-pointer"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </main>
  );
}
