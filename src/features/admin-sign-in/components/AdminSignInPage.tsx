import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@mzon7/zon-incubator-sdk/auth";

/**
 * Entry point for admin sign-in.
 * If already authenticated, redirects straight to /admin/devices.
 * Otherwise, redirects to the existing /login page with a return URL.
 */
export default function AdminSignInPage() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (loading) return;
    if (user) {
      navigate("/admin/devices", { replace: true });
    } else {
      navigate("/login?redirectTo=/admin/devices", { replace: true });
    }
  }, [user, loading, navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-rose-50 via-pink-50 to-fuchsia-50">
      <div className="flex flex-col items-center gap-3">
        <div
          className="w-8 h-8 rounded-full border-2 border-t-transparent animate-spin"
          style={{ borderColor: "#f457bb", borderTopColor: "transparent" }}
        />
        <p className="text-sm text-gray-400">Redirecting...</p>
      </div>
    </div>
  );
}
