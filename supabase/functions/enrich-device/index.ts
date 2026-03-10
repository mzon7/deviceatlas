import { serve } from "https://deno.land/std@0.208.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

const GROK_API_KEY = Deno.env.get("GROK_API_KEY")!;
const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

const FDA_SYSTEM_PROMPT = `You are a medical device classification expert with deep knowledge of FDA regulatory taxonomy and global medical device categories.

Given FDA structured data about a medical device, return a JSON object with:
- "description": 2-3 sentence clinical description for healthcare professionals. Ground in the FDA classification data.
- "disease_states": list of {name, confidence} for medical conditions this device diagnoses, treats, or monitors. Use standard FDA medical terminology. confidence: "high" = definitively established, "medium" = likely, "low" = inferred. Limit to 1-4. Return [] if unclear.
- "enrichment_method": "fda_classification"

Return ONLY the JSON object.`;

const NON_FDA_SYSTEM_PROMPT = `You are a medical device classification expert.

Given a medical device trade name, classify its disease states using FDA medical taxonomy terminology (for cross-country consistency).

Return a JSON object with:
- "description": 2-3 sentence clinical description.
- "disease_states": list of {name, confidence}. Use standard disease names (e.g. "Type 2 Diabetes Mellitus", "Hypertension", "Osteoarthritis of the Knee"). confidence: "high" if clearly indicated, "medium" if likely, "low" if inferred. Limit 1-4. Return [] if genuinely unclear.
- "enrichment_method": "gpt_inferred"

Return ONLY the JSON object.`;

async function callGrok(system: string, user: string): Promise<Record<string, unknown> | null> {
  const res = await fetch("https://api.x.ai/v1/chat/completions", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${GROK_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "grok-4-1-fast-non-reasoning",
      messages: [
        { role: "system", content: system },
        { role: "user", content: user },
      ],
      temperature: 0.1,
      max_tokens: 600,
    }),
  });
  if (!res.ok) throw new Error(`Grok ${res.status}: ${await res.text()}`);
  const data = await res.json();
  let content: string = data.choices[0].message.content.trim();
  content = content.replace(/^```(?:json)?\s*/m, "").replace(/\s*```\s*$/m, "").trim();
  return JSON.parse(content);
}

async function fetchFDAClassification(productCode: string): Promise<Record<string, string> | null> {
  try {
    const res = await fetch(
      `https://api.fda.gov/device/classification.json?search=product_code:${productCode}&limit=1`,
      { signal: AbortSignal.timeout(10000) }
    );
    if (!res.ok) return null;
    const data = await res.json();
    if (!data.results?.length) return null;
    const rec = data.results[0];
    return {
      generic_name: rec.device_name || "",
      specialty: rec.medical_specialty_description || "",
      device_class: rec.device_class || "",
      regulation_number: rec.regulation_number || "",
      definition: (rec.definition || "").slice(0, 500),
    };
  } catch {
    return null;
  }
}

function normalize(s: string): string {
  return s.toLowerCase().replace(/[^\w\s]/g, " ").replace(/\s+/g, " ").trim();
}

function jaccardSimilarity(a: string, b: string): number {
  const setA = new Set(a.split(" "));
  const setB = new Set(b.split(" "));
  const intersection = [...setA].filter(x => setB.has(x)).length;
  const union = new Set([...setA, ...setB]).size;
  return union > 0 ? intersection / union : 0;
}

function inferOrigin(dev: { clearance_type?: string; device_class?: string }): string {
  if (dev.clearance_type) return "FDA (USA)";
  const cl = dev.device_class || "";
  if (cl.startsWith("Class")) return "EU (EUDAMED)";
  if (["1", "2", "3", "4"].includes(cl)) return "Health Canada";
  return "International";
}

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

    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

    // Fetch device
    const { data: device, error: devErr } = await supabase
      .from("deviceatlas_devices")
      .select("id, name, manufacturer, product_code, device_class, clearance_type, submission_number, enrichment_method")
      .eq("id", deviceId)
      .single();

    if (devErr || !device) {
      return new Response(
        JSON.stringify({ data: null, error: "Device not found" }),
        { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Already enriched — skip
    if (device.enrichment_method && device.enrichment_method !== "not_enriched") {
      return new Response(
        JSON.stringify({ data: { already_enriched: true }, error: null }),
        { headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // ── Enrich ──────────────────────────────────────────────────────────────
    let result: Record<string, unknown> | null = null;
    let finalMethod = "gpt_inferred";
    let source = "";

    if (device.product_code) {
      const classification = await fetchFDAClassification(device.product_code);
      if (classification && (classification.generic_name || classification.specialty)) {
        const context = [
          `Trade name: ${device.name}`,
          `FDA generic name: ${classification.generic_name}`,
          `FDA medical specialty: ${classification.specialty}`,
          `FDA device class: ${classification.device_class}`,
          `FDA regulation: ${classification.regulation_number}`,
          classification.definition ? `FDA definition: ${classification.definition}` : "",
        ].filter(Boolean).join("\n");
        result = await callGrok(FDA_SYSTEM_PROMPT, context);
        finalMethod = "fda_classification";
        const k = device.submission_number || "";
        source = `FDA Product Classification (code: ${device.product_code}, generic: '${classification.generic_name}')`;
        if (k && k.toUpperCase().startsWith("K") && k.length >= 3 && /^\d/.test(k[1])) {
          source += `; 510(k) https://www.accessdata.fda.gov/cdrh_docs/pdf${k.slice(1, 3)}/${k}.pdf`;
        }
      } else {
        const origin = inferOrigin(device);
        const ctx = `Device trade name: ${device.name}\nRegulatory origin: ${origin}${device.device_class ? `\nDevice risk class: ${device.device_class}` : ""}\n(No FDA classification data — classify using FDA disease taxonomy for consistency)`;
        result = await callGrok(NON_FDA_SYSTEM_PROMPT, ctx);
        source = `FDA product_code ${device.product_code} (no classification data); trade name inference`;
      }
    } else {
      const origin = inferOrigin(device);
      const classInfo = device.device_class ? `, device class ${device.device_class}` : "";
      const ctx = `Device trade name: ${device.name}\nRegulatory origin: ${origin}${device.device_class ? `\nDevice risk class: ${device.device_class}` : ""}\n(No FDA product code — classify using FDA disease taxonomy for consistency)`;
      result = await callGrok(NON_FDA_SYSTEM_PROMPT, ctx);
      source = `Inferred from ${origin} device trade name${classInfo}. Disease states aligned to FDA medical taxonomy.`;
    }

    if (!result) {
      await supabase.from("deviceatlas_devices").update({
        enrichment_method: "not_enriched",
        enrichment_confidence: "low",
        updated_at: new Date().toISOString(),
      }).eq("id", deviceId);
      return new Response(
        JSON.stringify({ data: { enriched: false, reason: "AI returned no result" }, error: null }),
        { headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const description = (result.description as string) || "";
    const diseaseStatesRaw = (result.disease_states as Array<{ name: string; confidence: string }>) || [];

    const confidence =
      finalMethod === "fda_classification"
        ? diseaseStatesRaw.some(d => d.confidence === "high") ? "high" : "medium"
        : diseaseStatesRaw.some(d => ["high", "medium"].includes(d.confidence)) ? "medium" : "low";

    const indicationsText = diseaseStatesRaw
      .map(d => `${d.name} [${d.confidence || "medium"}]`)
      .join("; ");

    // ── Resolve / create disease states ────────────────────────────────────
    const { data: existingDS } = await supabase
      .from("deviceatlas_disease_states")
      .select("id, name");

    const dsCache = new Map<string, string>();
    for (const ds of existingDS || []) {
      dsCache.set(normalize(ds.name), ds.id);
    }

    const sorted = [...diseaseStatesRaw].sort((a, b) => {
      const order: Record<string, number> = { high: 0, medium: 1, low: 2 };
      return (order[a.confidence] ?? 2) - (order[b.confidence] ?? 2);
    });

    const dsIds: string[] = [];
    for (const ds of sorted) {
      const name = (ds.name || "").trim();
      if (!name) continue;
      const norm = normalize(name);

      if (dsCache.has(norm)) {
        const id = dsCache.get(norm)!;
        if (!dsIds.includes(id)) dsIds.push(id);
        continue;
      }

      // Fuzzy match
      let bestScore = 0, bestId = "";
      for (const [cNorm, cId] of dsCache.entries()) {
        const score = jaccardSimilarity(norm, cNorm);
        if (score > bestScore) { bestScore = score; bestId = cId; }
      }
      if (bestScore >= 0.85 && bestId) {
        dsCache.set(norm, bestId);
        if (!dsIds.includes(bestId)) dsIds.push(bestId);
        continue;
      }

      // Create new disease state
      const newId = crypto.randomUUID();
      const titleName = name.replace(/\b\w/g, c => c.toUpperCase());
      await supabase.from("deviceatlas_disease_states").insert({ id: newId, name: titleName });
      dsCache.set(norm, newId);
      if (!dsIds.includes(newId)) dsIds.push(newId);
    }

    // ── Update approvals with disease states ────────────────────────────────
    if (dsIds.length > 0) {
      const { data: existingApprovals } = await supabase
        .from("deviceatlas_approvals")
        .select("id, country, source_ref, approval_date, status, is_active")
        .eq("device_id", deviceId);

      if (existingApprovals && existingApprovals.length > 0) {
        const byCountry: Record<string, typeof existingApprovals[0][]> = {};
        for (const a of existingApprovals) {
          byCountry[a.country] = byCountry[a.country] || [];
          byCountry[a.country].push(a);
        }

        await supabase.from("deviceatlas_approvals").delete()
          .in("id", existingApprovals.map(a => a.id));

        const newApprovals = [];
        for (const [country, rows] of Object.entries(byCountry)) {
          const primary = rows[0];
          for (const dsId of dsIds) {
            newApprovals.push({
              device_id: deviceId,
              disease_state_id: dsId,
              country,
              status: primary.status || "Approved",
              approval_date: primary.approval_date,
              source_ref: primary.source_ref,
              is_active: primary.is_active ?? true,
            });
          }
        }
        if (newApprovals.length > 0) {
          await supabase.from("deviceatlas_approvals").insert(newApprovals);
        }
      }
    }

    // ── Save enrichment to device ───────────────────────────────────────────
    await supabase.from("deviceatlas_devices").update({
      description: description || null,
      indications_text: indicationsText || null,
      indications_source: source,
      enrichment_method: finalMethod,
      enrichment_confidence: confidence,
      updated_at: new Date().toISOString(),
    }).eq("id", deviceId);

    return new Response(
      JSON.stringify({
        data: {
          enriched: true,
          enrichment_method: finalMethod,
          confidence,
          disease_states: diseaseStatesRaw,
        },
        error: null,
      }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Internal server error";
    console.error("enrich-device error:", msg);
    return new Response(
      JSON.stringify({ data: null, error: msg }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
