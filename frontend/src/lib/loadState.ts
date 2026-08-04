// Generic three-state load lifecycle used by every page that fetches its
// own data: loading, error (with a user-facing message), or ready (with
// the data). One shared shape so every page's loading/error UI is driven
// by the same states, instead of a near-identical redeclaration per page.
export type LoadState<T> =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: T };
