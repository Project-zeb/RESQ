import { apiRequest } from "./api.js";

export async function fetchSessionUser() {
  const payload = await apiRequest("/auth/session");
  if (
    payload &&
    typeof payload === "object" &&
    "authenticated" in payload &&
    payload.authenticated &&
    "user" in payload &&
    payload.user &&
    typeof payload.user === "object"
  ) {
    return payload.user;
  }
  return null;
}

export function getUserFirstName(user) {
  if (!user || typeof user !== "object") {
    return "User";
  }

  const rawName =
    ("name" in user && typeof user.name === "string" && user.name.trim()) ||
    ("username" in user && typeof user.username === "string" && user.username.trim()) ||
    "";

  if (!rawName) {
    return "User";
  }

  return rawName.split(/\s+/)[0] || "User";
}

export function getUserRoleLabel(user) {
  if (!user || typeof user !== "object") {
    return "User";
  }

  const rawRole =
    ("account_type" in user && typeof user.account_type === "string" && user.account_type) ||
    ("role" in user && typeof user.role === "string" && user.role) ||
    ("user_type" in user && typeof user.user_type === "string" && user.user_type) ||
    "";

  if (!rawRole) {
    return "User";
  }

  const normalized = rawRole.trim().replace(/\s+/g, "_").toUpperCase();
  if (!normalized) {
    return "User";
  }

  const normalizedAccountType =
    normalized === "OFFICER"
      ? "USER"
      : normalized === "ORGANISATION"
        ? "ORGANIZATION"
        : normalized;

  return normalizedAccountType
    .split("_")
    .map((segment) => segment.charAt(0) + segment.slice(1).toLowerCase())
    .join(" ");
}

export async function fetchProfileDetails() {
  const payload = await apiRequest("/auth/profile");
  if (
    payload &&
    typeof payload === "object" &&
    "success" in payload &&
    payload.success &&
    "profile" in payload &&
    payload.profile &&
    typeof payload.profile === "object"
  ) {
    return payload.profile;
  }
  return null;
}

export async function updateProfileDetails(updates) {
  const payload = await apiRequest("/auth/profile", {
    method: "POST",
    body: updates
  });
  if (
    payload &&
    typeof payload === "object" &&
    "success" in payload &&
    payload.success &&
    "profile" in payload &&
    payload.profile &&
    typeof payload.profile === "object"
  ) {
    return payload.profile;
  }
  return null;
}

export async function logoutSession() {
  return apiRequest("/auth/logout", { method: "POST" });
}
