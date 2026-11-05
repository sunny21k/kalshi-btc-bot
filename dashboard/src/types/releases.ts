export type ReleaseNote = { version: string; date: string; title: string; changes: string[] };
export type ReleaseInfo = { version: string; sourceHash: string; releases: ReleaseNote[] };
