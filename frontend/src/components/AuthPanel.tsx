import { useState } from "react";

interface AuthPanelProps {
  onLogin: (payload: {
    identifier: string;
    password: string;
    rememberMe: boolean;
  }) => Promise<void>;
  onSignup: (payload: {
    name: string;
    username: string;
    email: string;
    password: string;
    rememberMe: boolean;
  }) => Promise<void>;
}

export function AuthPanel({ onLogin, onSignup }: AuthPanelProps) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [rememberMeLogin, setRememberMeLogin] = useState(false);
  const [rememberMeSignup, setRememberMeSignup] = useState(false);
  const [loginForm, setLoginForm] = useState({ identifier: "", password: "" });
  const [signupForm, setSignupForm] = useState({
    name: "",
    username: "",
    email: "",
    password: "",
  });

  return (
    <div className="mx-auto max-w-5xl px-6 py-16 lg:px-8">
      <div className="rounded-[2.5rem] border border-white/10 bg-white/5 p-8 shadow-2xl shadow-slate-950/50 backdrop-blur">
        <div className="mb-8 inline-flex rounded-full border border-cyan-400/20 bg-cyan-400/10 px-4 py-1 text-xs font-semibold uppercase tracking-[0.25em] text-cyan-100">
          Alpha Agent Builder
        </div>
        <div className="grid gap-8 lg:grid-cols-[1.1fr_0.9fr]">
          <div>
            <h1 className="text-4xl font-semibold tracking-tight text-white md:text-5xl">
              Sign in to create, store, and run your generated agents.
            </h1>
            <p className="mt-4 max-w-2xl text-base leading-7 text-slate-300">
              Your account stores API keys, GitHub access, generated agents, uploaded files, and
              personal settings in SQLite so the workspace becomes persistent and user-specific.
              By default your sign-in lasts for this browser session only; check &quot;Keep me signed in&quot; if you
              want to skip login after closing the browser (same as older versions that always remembered you).
            </p>
            <div className="mt-8 grid gap-4 md:grid-cols-2">
              {[
                "Login and account settings",
                "Saved API keys and GitHub token",
                "Generated agent history per user",
                "GitHub repo check-in on generation",
              ].map((item) => (
                <div key={item} className="rounded-2xl border border-white/10 bg-slate-950/40 px-4 py-4 text-sm text-slate-200">
                  {item}
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-[2rem] border border-white/10 bg-slate-950/50 p-6">
            <div className="mb-5 flex gap-2 rounded-full bg-white/5 p-1">
              <button
                className={`flex-1 rounded-full px-4 py-2 text-sm font-medium transition ${
                  mode === "login" ? "bg-cyan-400/90 text-slate-950" : "text-slate-300"
                }`}
                onClick={() => setMode("login")}
                type="button"
              >
                Login
              </button>
              <button
                className={`flex-1 rounded-full px-4 py-2 text-sm font-medium transition ${
                  mode === "signup" ? "bg-cyan-400/90 text-slate-950" : "text-slate-300"
                }`}
                onClick={() => setMode("signup")}
                type="button"
              >
                Sign Up
              </button>
            </div>

            {mode === "login" ? (
              <form
                className="space-y-4"
                onSubmit={(event) => {
                  event.preventDefault();
                  void onLogin({ ...loginForm, rememberMe: rememberMeLogin });
                }}
              >
                <input
                  className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:border-cyan-400/60 focus:outline-none"
                  onChange={(event) =>
                    setLoginForm((current) => ({ ...current, identifier: event.target.value }))
                  }
                  placeholder="Username or email"
                  value={loginForm.identifier}
                />
                <input
                  className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:border-cyan-400/60 focus:outline-none"
                  onChange={(event) =>
                    setLoginForm((current) => ({ ...current, password: event.target.value }))
                  }
                  placeholder="Password"
                  type="password"
                  value={loginForm.password}
                />
                <label className="flex cursor-pointer items-center gap-3 text-sm text-slate-300">
                  <input
                    checked={rememberMeLogin}
                    className="h-4 w-4 accent-cyan-400"
                    onChange={(event) => setRememberMeLogin(event.target.checked)}
                    type="checkbox"
                  />
                  <span>Keep me signed in on this device (uses browser storage until you log out)</span>
                </label>
                <button
                  className="w-full rounded-full bg-gradient-to-r from-cyan-400 via-sky-400 to-violet-500 px-5 py-3 text-sm font-semibold text-slate-950 shadow-lg shadow-cyan-500/20 transition hover:scale-[1.01]"
                  type="submit"
                >
                  Login
                </button>
              </form>
            ) : (
              <form
                className="space-y-4"
                onSubmit={(event) => {
                  event.preventDefault();
                  void onSignup({ ...signupForm, rememberMe: rememberMeSignup });
                }}
              >
                <input
                  className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:border-cyan-400/60 focus:outline-none"
                  onChange={(event) =>
                    setSignupForm((current) => ({ ...current, name: event.target.value }))
                  }
                  placeholder="Full name"
                  value={signupForm.name}
                />
                <input
                  className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:border-cyan-400/60 focus:outline-none"
                  onChange={(event) =>
                    setSignupForm((current) => ({ ...current, username: event.target.value }))
                  }
                  placeholder="Username"
                  value={signupForm.username}
                />
                <input
                  className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:border-cyan-400/60 focus:outline-none"
                  onChange={(event) =>
                    setSignupForm((current) => ({ ...current, email: event.target.value }))
                  }
                  placeholder="Email"
                  type="email"
                  value={signupForm.email}
                />
                <input
                  className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:border-cyan-400/60 focus:outline-none"
                  onChange={(event) =>
                    setSignupForm((current) => ({ ...current, password: event.target.value }))
                  }
                  placeholder="Password"
                  type="password"
                  value={signupForm.password}
                />
                <label className="flex cursor-pointer items-center gap-3 text-sm text-slate-300">
                  <input
                    checked={rememberMeSignup}
                    className="h-4 w-4 accent-cyan-400"
                    onChange={(event) => setRememberMeSignup(event.target.checked)}
                    type="checkbox"
                  />
                  <span>Keep me signed in on this device (uses browser storage until you log out)</span>
                </label>
                <button
                  className="w-full rounded-full bg-gradient-to-r from-cyan-400 via-sky-400 to-violet-500 px-5 py-3 text-sm font-semibold text-slate-950 shadow-lg shadow-cyan-500/20 transition hover:scale-[1.01]"
                  type="submit"
                >
                  Create account
                </button>
              </form>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
