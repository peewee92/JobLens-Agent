/** Stale facts block new preparation, not reading the historical workspace. */
export async function readOptionalPreparation<T>(read: () => Promise<T>): Promise<T | null> {
  try {
    return await read();
  } catch (error) {
    if (error instanceof Error && "status" in error && error.status === 409 &&
        "code" in error && error.code === "application_workspace_facts_stale") return null;
    throw error;
  }
}
