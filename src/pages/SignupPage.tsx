import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@mzon7/zon-incubator-sdk/auth";

export default function SignupPage() {
  const { signUp } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    const { error: err, needsConfirmation } = await signUp(email, password);
    setLoading(false);
    if (err) {
      setError(err);
    } else if (needsConfirmation) {
      setSuccess(true);
    }
  };

  const bgStyle = {
    background:
      "linear-gradient(135deg, #fdf2fb 0%, #fce7f3 40%, #fdf4ff 70%, #fff1f5 100%)",
  };

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4" style={bgStyle}>
        <div
          className="w-full max-w-sm rounded-2xl p-8 text-center space-y-5"
          style={{
            background: "rgba(255,255,255,0.75)",
            backdropFilter: "blur(20px)",
            border: "1px solid rgba(244,87,187,0.18)",
            boxShadow: "0 8px 40px rgba(244,87,187,0.10)",
          }}
        >
          <div
            className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto"
            style={{ background: "rgba(244,87,187,0.08)" }}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="#f457bb"
              className="w-7 h-7"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75"
              />
            </svg>
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900">Check your email</h1>
            <p className="text-sm text-gray-500 mt-2 leading-relaxed">
              We sent a confirmation link to{" "}
              <span className="font-medium text-gray-700">{email}</span>. Click
              the link to activate your account.
            </p>
          </div>
          <Link
            to="/login"
            className="inline-flex items-center gap-1.5 text-sm font-semibold"
            style={{ color: "#f457bb" }}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={2}
              stroke="currentColor"
              className="w-4 h-4"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
            </svg>
            Back to sign in
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4" style={bgStyle}>
      {/* Background orbs */}
      <div
        className="fixed top-[-100px] right-[-100px] w-[400px] h-[400px] rounded-full pointer-events-none"
        style={{ background: "radial-gradient(circle, rgba(244,87,187,0.15) 0%, transparent 70%)" }}
      />
      <div
        className="fixed bottom-[-80px] left-[-80px] w-[300px] h-[300px] rounded-full pointer-events-none"
        style={{ background: "radial-gradient(circle, rgba(234,16,92,0.10) 0%, transparent 70%)" }}
      />

      <div className="w-full max-w-sm relative">
        {/* Logo mark */}
        <div className="flex flex-col items-center mb-8 gap-3">
          <div
            className="w-12 h-12 rounded-2xl flex items-center justify-center shadow-lg"
            style={{ background: "linear-gradient(135deg, #f457bb, #ea105c)" }}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="white"
              className="w-6 h-6"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z"
              />
            </svg>
          </div>
          <div className="text-center">
            <h1 className="text-xl font-bold text-gray-900 tracking-tight">DeviceAtlas</h1>
            <p className="text-xs text-gray-400 mt-0.5">Medical Device Approval Platform</p>
          </div>
        </div>

        {/* Card */}
        <div
          className="rounded-2xl p-8 space-y-6"
          style={{
            background: "rgba(255,255,255,0.75)",
            backdropFilter: "blur(20px)",
            border: "1px solid rgba(244,87,187,0.18)",
            boxShadow: "0 8px 40px rgba(244,87,187,0.10), 0 1px 0 rgba(255,255,255,0.8) inset",
          }}
        >
          <div>
            <h2 className="text-2xl font-bold text-gray-900">Create account</h2>
            <p className="text-sm text-gray-400 mt-1">Get started today</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1.5">
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="block w-full rounded-xl px-4 py-2.5 text-gray-900 text-sm placeholder-gray-400 outline-none"
                style={{
                  background: "rgba(255,255,255,0.8)",
                  border: "1.5px solid rgba(244,87,187,0.2)",
                  boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
                }}
                onFocus={(e) => (e.currentTarget.style.border = "1.5px solid rgba(244,87,187,0.6)")}
                onBlur={(e) => (e.currentTarget.style.border = "1.5px solid rgba(244,87,187,0.2)")}
                placeholder="you@example.com"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1.5">
                Password
              </label>
              <input
                id="password"
                type="password"
                required
                minLength={6}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="block w-full rounded-xl px-4 py-2.5 text-gray-900 text-sm placeholder-gray-400 outline-none"
                style={{
                  background: "rgba(255,255,255,0.8)",
                  border: "1.5px solid rgba(244,87,187,0.2)",
                  boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
                }}
                onFocus={(e) => (e.currentTarget.style.border = "1.5px solid rgba(244,87,187,0.6)")}
                onBlur={(e) => (e.currentTarget.style.border = "1.5px solid rgba(244,87,187,0.2)")}
                placeholder="••••••••"
              />
            </div>

            {error && (
              <div
                className="rounded-xl px-4 py-3 text-sm"
                style={{
                  background: "rgba(234,16,92,0.06)",
                  border: "1px solid rgba(234,16,92,0.2)",
                  color: "#ea105c",
                }}
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl py-2.5 text-sm font-semibold text-white disabled:opacity-60 disabled:cursor-not-allowed"
              style={{
                background: loading ? "rgba(244,87,187,0.7)" : "linear-gradient(135deg, #f457bb, #ea105c)",
                boxShadow: loading ? "none" : "0 4px 16px rgba(244,87,187,0.35)",
              }}
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span
                    className="w-4 h-4 rounded-full border-2 animate-spin"
                    style={{ borderColor: "rgba(255,255,255,0.4)", borderTopColor: "white" }}
                  />
                  Creating account...
                </span>
              ) : (
                "Create account"
              )}
            </button>
          </form>

          <p className="text-center text-sm text-gray-500">
            Already have an account?{" "}
            <Link to="/login" className="font-semibold" style={{ color: "#f457bb" }}>
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
