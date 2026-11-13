/** Tiny IndexedDB key-value store for the offline journal draft (FR-014, AC-011). Every call degrades to a no-op when storage is unavailable. */
const DB = 'cadence'
const STORE = 'kv'

function open(): Promise<IDBDatabase | null> {
  return new Promise((resolve) => {
    try {
      const req = indexedDB.open(DB, 1)
      req.onupgradeneeded = () => req.result.createObjectStore(STORE)
      req.onsuccess = () => resolve(req.result)
      req.onerror = () => resolve(null)
    } catch {
      resolve(null)
    }
  })
}

export async function idbGet<T>(key: string): Promise<T | undefined> {
  const db = await open()
  if (!db) return undefined
  return new Promise((resolve) => {
    const r = db.transaction(STORE).objectStore(STORE).get(key)
    r.onsuccess = () => resolve(r.result as T | undefined)
    r.onerror = () => resolve(undefined)
  })
}

export async function idbSet(key: string, value: unknown): Promise<void> {
  const db = await open()
  if (!db) return
  await new Promise<void>((resolve) => {
    const tx = db.transaction(STORE, 'readwrite')
    tx.objectStore(STORE).put(value, key)
    tx.oncomplete = () => resolve()
    tx.onerror = () => resolve()
  })
}

export async function idbDelete(key: string): Promise<void> {
  const db = await open()
  if (!db) return
  await new Promise<void>((resolve) => {
    const tx = db.transaction(STORE, 'readwrite')
    tx.objectStore(STORE).delete(key)
    tx.oncomplete = () => resolve()
    tx.onerror = () => resolve()
  })
}
