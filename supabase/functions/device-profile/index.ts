import { serve } from "https://deno.land/std@0.208.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const { deviceId } = await req.json();

    if (!deviceId) {
      return new Response(
        JSON.stringify({ data: null, error: "deviceId is required" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const supabase = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
    );

    // Fetch device
    const { data: device, error: deviceError } = await supabase
      .from("deviceatlas_devices")
      .select("*")
      .eq("id", deviceId)
      .single();

    if (deviceError || !device) {
      return new Response(
        JSON.stringify({ data: null, error: "Device not found" }),
        { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Fetch approvals with disease state info
    const { data: approvals, error: approvalsError } = await supabase
      .from("deviceatlas_approvals")
      .select(`
        id,
        country,
        status,
        approval_date,
        retired_date,
        source_ref,
        is_active,
        updated_at,
        disease_state:deviceatlas_disease_states(id, name, description)
      `)
      .eq("device_id", deviceId)
      .eq("is_active", true)
      .order("approval_date", { ascending: false });

    if (approvalsError) {
      throw approvalsError;
    }

    // Group by country
    const usApprovals = (approvals || []).filter((a) => a.country === "US");
    const caApprovals = (approvals || []).filter((a) => a.country === "CA");

    // Count summaries
    const summary = {
      us_count: usApprovals.length,
      ca_count: caApprovals.length,
      total_count: (approvals || []).length,
      us_approved_count: usApprovals.filter((a) => a.status === "Approved").length,
      ca_approved_count: caApprovals.filter((a) => a.status === "Approved").length,
    };

    return new Response(
      JSON.stringify({
        data: {
          device,
          approvals: approvals || [],
          us_approvals: usApprovals,
          ca_approvals: caApprovals,
          summary,
        },
        error: null,
      }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err) {
    console.error("device-profile error:", err);
    return new Response(
      JSON.stringify({ data: null, error: err.message || "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
