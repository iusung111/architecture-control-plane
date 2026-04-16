import type { ControlPlaneDatabase } from "../domain/types";

const STORAGE_KEY = "control-plane-db";

function emptyDatabase(): ControlPlaneDatabase {
  return { approvals: {}, cycles: {}, requests: {} };
}

export class ControlPlaneStore {
  private cache: ControlPlaneDatabase | null = null;

  constructor(private readonly state: DurableObjectState) {}

  async read(): Promise<ControlPlaneDatabase> {
    if (this.cache) {
      return this.cache;
    }
    const stored = await this.state.storage.get<ControlPlaneDatabase>(STORAGE_KEY);
    this.cache = stored ?? emptyDatabase();
    return this.cache;
  }

  async write<T>(mutate: (db: ControlPlaneDatabase) => T | Promise<T>): Promise<T> {
    const db = structuredClone(await this.read());
    const result = await mutate(db);
    this.cache = db;
    await this.state.storage.put(STORAGE_KEY, db);
    return result;
  }
}
