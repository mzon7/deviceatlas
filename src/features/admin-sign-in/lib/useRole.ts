import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@mzon7/zon-incubator-sdk/auth";
import { withDbErrorCapture } from "@mzon7/zon-incubator-sdk";
import { supabase, dbTable, PROJECT_PREFIX } from "../../../lib/supabase";

export type Role = "Admin" | "Editor" | "Viewer";

export function useRole() {
  const { user } = useAuth();

  const query = useQuery({
    queryKey: ["role", user?.id],
    enabled: !!user,
    staleTime: 5 * 60 * 1000, // 5 min
    queryFn: async (): Promise<Role | null> => {
      const { data, error } = await withDbErrorCapture(
        supabase,
        dbTable("roles"),
        supabase.from(dbTable("roles")).select("role").eq("user_id", user!.id).maybeSingle(),
        PROJECT_PREFIX,
      );

      if (error) throw new Error(error.message);
      return (data?.role as Role) ?? null;
    },
  });

  return {
    role: query.data ?? null,
    isLoading: query.isLoading,
    isAdmin: query.data === "Admin",
    isEditor: query.data === "Editor",
    isAdminOrEditor: query.data === "Admin" || query.data === "Editor",
  };
}
