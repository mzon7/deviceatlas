import { Navigate } from "react-router-dom";
import { useAuth } from "@mzon7/zon-incubator-sdk/auth";
import { useRole } from "../lib/useRole";
import AccessDenied from "./AccessDenied";

interface AdminRouteProps {
  children: React.ReactNode;
}

export default function AdminRoute({ children }: AdminRouteProps) {
  const { user, loading: authLoading } = useAuth();
  const { isAdminOrEditor, isLoading: roleLoading } = useRole();

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-rose-50 via-pink-50 to-fuchsia-50">
        <div className="flex flex-col items-center gap-3">
          <div
            className="w-8 h-8 rounded-full border-2 border-t-transparent animate-spin"
            style={{ borderColor: "#f457bb", borderTopColor: "transparent" }}
          />
          <p className="text-sm text-gray-400">Loading...</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login?redirectTo=/admin/devices" replace />;
  }

  if (roleLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-rose-50 via-pink-50 to-fuchsia-50">
        <div className="flex flex-col items-center gap-3">
          <div
            className="w-8 h-8 rounded-full border-2 border-t-transparent animate-spin"
            style={{ borderColor: "#f457bb", borderTopColor: "transparent" }}
          />
          <p className="text-sm text-gray-400">Verifying permissions...</p>
        </div>
      </div>
    );
  }

  if (!isAdminOrEditor) {
    return <AccessDenied />;
  }

  return <>{children}</>;
}
