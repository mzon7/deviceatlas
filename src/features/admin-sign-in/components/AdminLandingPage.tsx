import { useAuth } from "@mzon7/zon-incubator-sdk/auth";
import { useRole } from "../lib/useRole";

export default function AdminLandingPage() {
  const { user, signOut } = useAuth();
  const { role } = useRole();

  return (
    <div
      className="min-h-screen"
      style={{ background: "linear-gradient(135deg, #fdf2fb 0%, #fce7f3 50%, #fdf4ff 100%)" }}
    >
      <header
        className="border-b"
        style={{
          background: "rgba(255,255,255,0.7)",
          backdropFilter: "blur(12px)",
          borderColor: "rgba(244,87,187,0.15)",
        }}
      >
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center"
              style={{ background: "linear-gradient(135deg, #f457bb, #ea105c)" }}
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="white"
                className="w-4 h-4"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z"
                />
              </svg>
            </div>
            <span className="font-semibold text-gray-900">DeviceAtlas Admin</span>
          </div>

          <div className="flex items-center gap-4">
            {role && (
              <span
                className="text-xs font-medium px-2.5 py-1 rounded-full"
                style={{
                  background: "rgba(244,87,187,0.1)",
                  color: "#ea105c",
                  border: "1px solid rgba(244,87,187,0.2)",
                }}
              >
                {role}
              </span>
            )}
            <span className="text-sm text-gray-500">{user?.email}</span>
            <button
              onClick={signOut}
              className="text-sm text-gray-500 hover:text-gray-800 transition-colors font-medium"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-12">
        <div className="space-y-2 mb-10">
          <h1 className="text-3xl font-bold text-gray-900">Manage Devices</h1>
          <p className="text-gray-500">
            Add, update, and track medical device approvals across Canada and USA.
          </p>
        </div>

        <div
          className="rounded-2xl p-8 text-center"
          style={{
            background: "rgba(255,255,255,0.6)",
            backdropFilter: "blur(16px)",
            border: "1px solid rgba(244,87,187,0.15)",
            boxShadow: "0 4px 24px rgba(244,87,187,0.08)",
          }}
        >
          <div
            className="w-12 h-12 rounded-xl flex items-center justify-center mx-auto mb-4"
            style={{ background: "rgba(244,87,187,0.08)" }}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="#f457bb"
              className="w-6 h-6"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M11.42 15.17L17.25 21A2.652 2.652 0 0021 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 11-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 004.486-6.336l-3.276 3.277a3.004 3.004 0 01-2.25-2.25l3.276-3.276a4.5 4.5 0 00-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085m-1.745 1.437L5.909 7.5H4.5L2.25 3.75l1.5-1.5L7.5 4.5v1.409l4.26 4.26m-1.745 1.437l1.745-1.437m6.615 8.206L15.75 15.75M4.867 19.125h.008v.008h-.008v-.008z"
              />
            </svg>
          </div>
          <p className="text-gray-400 text-sm">
            Device management features coming soon.
          </p>
        </div>
      </main>
    </div>
  );
}
