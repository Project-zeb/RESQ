import React, { useEffect, useState } from "react";
import baseStyles from "/styles.module.css";
import pageStyles from "/profile.module.css";
import { Link, useNavigate } from "react-router-dom";
import { cx } from "../utils/cx.js";
import {
  fetchProfileDetails,
  getUserFirstName,
  logoutSession,
  updateProfileDetails
} from "../utils/session.js";

const c = (classNames) => cx(classNames, baseStyles, pageStyles);

function toFormState(profile) {
  return {
    masked_id: profile?.masked_id || "",
    account_type: profile?.account_type || "USER",
    name: profile?.name || "",
    username: profile?.username || "",
    email: profile?.email || "",
    phone: profile?.phone || "",
    password: profile?.password || "Hidden for security"
  };
}

export default function ProfilePage() {
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [sessionUser, setSessionUser] = useState(null);
  const [formData, setFormData] = useState(toFormState(null));
  const [isLoading, setIsLoading] = useState(true);
  const [needsAuth, setNeedsAuth] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [notice, setNotice] = useState({ type: "", text: "" });

  useEffect(() => {
    let active = true;

    const loadProfile = async () => {
      setIsLoading(true);
      setNotice({ type: "", text: "" });
      try {
        const profile = await fetchProfileDetails();
        if (!active) {
          return;
        }
        if (!profile) {
          setNeedsAuth(true);
          return;
        }
        setNeedsAuth(false);
        setFormData(toFormState(profile));
        setSessionUser({
          name: profile.name,
          username: profile.username,
          role: profile.account_type
        });
      } catch (error) {
        if (!active) {
          return;
        }
        if (error && typeof error === "object" && "status" in error && error.status === 401) {
          setNeedsAuth(true);
          setNotice({ type: "error", text: "Please log in to view profile details." });
        } else {
          const message =
            error instanceof Error ? error.message : "Unable to load profile details.";
          setNotice({ type: "error", text: message });
        }
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    };

    loadProfile();
    return () => {
      active = false;
    };
  }, []);

  const handleChange = (event) => {
    const { name, value } = event.target;
    setFormData((current) => ({
      ...current,
      [name]: value
    }));
  };

  const handleEditToggle = () => {
    if (needsAuth) {
      navigate("/login");
      return;
    }
    setNotice({ type: "", text: "" });
    setIsEditing((current) => !current);
  };

  const handleSave = async () => {
    if (needsAuth) {
      navigate("/login");
      return;
    }
    setIsSaving(true);
    setNotice({ type: "", text: "" });
    try {
      const profile = await updateProfileDetails({
        name: formData.name,
        phone: formData.phone
      });
      if (profile) {
        setFormData(toFormState(profile));
        setSessionUser({
          name: profile.name,
          username: profile.username,
          role: profile.account_type
        });
      }
      setIsEditing(false);
      setNotice({ type: "success", text: "Profile updated successfully." });
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to save profile changes.";
      setNotice({ type: "error", text: message });
    } finally {
      setIsSaving(false);
    }
  };

  const handleLogout = async () => {
    try {
      await logoutSession();
    } catch (_error) {
      // Redirect even if logout endpoint returns an error.
    }
    navigate("/", { replace: true });
  };

  return (
    <div className={c("page-profile")}>
      <div className={c("cloud-overlay")} />
      <header className={c("top-nav")}>
        <div
          className={c("nav-content")}
          data-mobile-menu={mobileMenuOpen ? "open" : "closed"}
        >
          <div className={c("nav-left")}>
            <div className={c("logo")}>
              <Link to="/" className={c("logo-container")} style={{ textDecoration: "none" }}>
                <img src="/logo.png" alt="Resqfy Logo" className={c("main-logo")} />
              </Link>
            </div>
            <nav
              className={c("nav-links")}
              id="profile-primary-nav"
              onClick={() => setMobileMenuOpen(false)}
            >
              <Link to="/">Home</Link>
              <Link to="/alerts">Alerts</Link>
              <Link to="/satellite">Satellite / Geo</Link>
              <Link to="/profile" className={c("active")}>Profile</Link>
            </nav>
          </div>
          <div className={c("nav-right")}>
            <div className={c("theme-toggle")}>
              <button
                className={c("toggle-btn")}
                data-theme-toggle
                aria-label="Toggle theme"
              >
                <svg className={c("sun")} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><circle cx={12} cy={12} r={5} /><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" /></svg>
                <div className={c("toggle-track")}><div className={c("toggle-thumb")} /></div>
                <svg className={c("moon")} viewBox="0 0 24 24" fill="currentColor"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" /></svg>
              </button>
            </div>
            <button
              className={c("mobile-menu-btn")}
              type="button"
              aria-label="Toggle navigation menu"
              aria-controls="profile-primary-nav"
              aria-expanded={mobileMenuOpen}
              onClick={() => setMobileMenuOpen((open) => !open)}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
                {mobileMenuOpen ? (
                  <>
                    <path d="M6 6l12 12" />
                    <path d="M18 6l-12 12" />
                  </>
                ) : (
                  <>
                    <path d="M3 6h18" />
                    <path d="M3 12h18" />
                    <path d="M3 18h18" />
                  </>
                )}
              </svg>
            </button>
            <div className={c("user-profile")}>
              <img src="/profile-icon.svg" alt="User profile" className={c("avatar")} />
              <div className={c("user-info")}>
                <span className={c("name")}>{getUserFirstName(sessionUser)}</span>
              </div>
              <svg className={c("chevron")} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><polyline points="6 9 12 15 18 9" /></svg>
            </div>
          </div>
        </div>
      </header>

      <div className={c("dashboard-container profile-shell")}>
        <section className={c("panel profile-card")}>
          <div className={c("profile-head")}>
            <div>
              <h1 className={c("profile-title")}>Profile Info</h1>
              <p className={c("profile-subtitle")}>Manage your account details</p>
            </div>
            <Link to="/" className={c("close-link")}>Close</Link>
          </div>

          {notice.text ? (
            <p
              className={c(
                notice.type === "error" ? "notice notice-error" : "notice notice-success"
              )}
            >
              {notice.text}
            </p>
          ) : null}

          {isLoading ? (
            <div className={c("loading-box")}>Loading profile details...</div>
          ) : null}

          {!isLoading && needsAuth ? (
            <div className={c("auth-box")}>
              <p className={c("auth-text")}>Log in to open your profile details and edit account data.</p>
              <div className={c("button-row")}>
                <Link to="/login" className={c("action-btn action-primary")}>Log In</Link>
                <Link to="/" className={c("action-btn action-ghost")}>Back Home</Link>
              </div>
            </div>
          ) : null}

          {!isLoading && !needsAuth ? (
            <>
              <div className={c("summary-grid")}>
                <div className={c("summary-item")}>
                  <span>Masked ID</span>
                  <strong>{formData.masked_id || "-"}</strong>
                </div>
                <div className={c("summary-item")}>
                  <span>Account Type</span>
                  <strong>{formData.account_type || "-"}</strong>
                </div>
              </div>

              <div className={c("form-grid")}>
                <label className={c("field")}>
                  <span>Name</span>
                  <input
                    name="name"
                    value={formData.name}
                    onChange={handleChange}
                    readOnly={!isEditing}
                  />
                </label>
                <label className={c("field")}>
                  <span>Username</span>
                  <input
                    name="username"
                    value={formData.username}
                    readOnly
                    disabled
                  />
                </label>
                <label className={c("field")}>
                  <span>Email</span>
                  <input
                    name="email"
                    type="email"
                    value={formData.email}
                    readOnly
                    disabled
                  />
                </label>
                <label className={c("field")}>
                  <span>Password</span>
                  <input name="password" value={formData.password} readOnly />
                </label>
                <label className={c("field field-full")}>
                  <span>Phone</span>
                  <input
                    name="phone"
                    value={formData.phone}
                    onChange={handleChange}
                    readOnly={!isEditing}
                  />
                </label>
              </div>

              <div className={c("button-row")}>
                <button
                  type="button"
                  className={c("action-btn action-ghost")}
                  onClick={handleEditToggle}
                  disabled={isSaving}
                >
                  {isEditing ? "Cancel" : "Edit"}
                </button>
                <button
                  type="button"
                  className={c("action-btn action-primary")}
                  onClick={handleSave}
                  disabled={!isEditing || isSaving}
                >
                  {isSaving ? "Saving..." : "Save Changes"}
                </button>
                <button
                  type="button"
                  className={c("action-btn action-danger")}
                  onClick={handleLogout}
                  disabled={isSaving}
                >
                  Log Out
                </button>
              </div>
            </>
          ) : null}
        </section>
      </div>
    </div>
  );
}
