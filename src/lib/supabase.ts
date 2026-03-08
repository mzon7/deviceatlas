import { createProjectClient } from "@mzon7/zon-incubator-sdk";

export const PROJECT_PREFIX = "deviceatlas_";
export const { supabase, dbTable } = createProjectClient(PROJECT_PREFIX);
