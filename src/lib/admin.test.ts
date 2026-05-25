import { describe, it, expect } from "vitest";
import { isAdmin, ADMIN_EMAILS } from "./admin";

describe("isAdmin", () => {
  it("returns true for keller.scholl@gmail.com (the canonical admin)", () => {
    expect(isAdmin("keller.scholl@gmail.com")).toBe(true);
  });

  it("returns false for any non-admin email", () => {
    expect(isAdmin("someone-else@gmail.com")).toBe(false);
    expect(isAdmin("admin@example.com")).toBe(false);
  });

  it("tolerates null / undefined / empty without throwing", () => {
    // session.user?.email may be undefined; the predicate handles it.
    expect(isAdmin(undefined)).toBe(false);
    expect(isAdmin(null)).toBe(false);
    expect(isAdmin("")).toBe(false);
  });

  it("is case-sensitive (matches Google's lowercase-normalized form)", () => {
    // Google OAuth normalizes Gmail addresses to lowercase. If a user
    // somehow ends up with uppercase in the email column, that's a
    // signal something is wrong — don't paper over it.
    expect(isAdmin("Keller.Scholl@gmail.com")).toBe(false);
    expect(isAdmin("KELLER.SCHOLL@GMAIL.COM")).toBe(false);
  });

  it("does not match on prefix / suffix / lookalike domains", () => {
    expect(isAdmin("keller.scholl@gmail.co")).toBe(false);
    expect(isAdmin("keller.scholl@gmail.com.evil.com")).toBe(false);
    expect(isAdmin("keller.scholl+attacker@gmail.com")).toBe(false);
  });

  it("ADMIN_EMAILS set is small (single admin today, accidental growth is a smell)", () => {
    // Sanity ceiling. If this is failing, the admin list grew —
    // probably intentional, but worth a deliberate test bump rather
    // than silent drift.
    expect(ADMIN_EMAILS.size).toBeLessThanOrEqual(3);
  });
});
