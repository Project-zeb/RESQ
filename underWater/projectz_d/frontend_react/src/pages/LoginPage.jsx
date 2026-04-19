import React, { useEffect, useState } from "react";
import baseStyles from "/styles.module.css";
import authStyles from "/auth.module.css";
import { Link, useNavigate } from "react-router-dom";
import { apiRequest } from "../utils/api.js";
import { cx } from "../utils/cx.js";

const c = (classNames) => cx(classNames, baseStyles, authStyles);

export default function LoginPage() {
  const navigate = useNavigate();
  const [theme, setTheme] = useState(
    () => localStorage.getItem("theme") || "dark"
  );
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  const [formSuccess, setFormSuccess] = useState("");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((currentTheme) => (currentTheme === "light" ? "dark" : "light"));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    setFormError("");
    setFormSuccess("");

    if (!identifier.trim() || !password.trim()) {
      setFormError("Please enter username/email and password.");
      return;
    }

    setIsSubmitting(true);
    try {
      const result = await apiRequest("/auth/login", {
        method: "POST",
        body: {
          username: identifier.trim(),
          password
        }
      });

      const destination =
        typeof result === "object" &&
        result &&
        "user" in result &&
        result.user &&
        typeof result.user === "object" &&
        "is_admin" in result.user &&
        result.user.is_admin
          ? "/admin"
          : "/";
      setFormSuccess("Login successful. Redirecting...");
      window.setTimeout(() => {
        navigate(destination, { replace: true });
      }, 200);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Login failed.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className={c("page-auth login-page")}>
      <div className={c("auth-shell")}>
        <section className={c("brand-panel")}>
          <div className={c("brand-overlay")} />
          <div className={c("brand-content")}>
            <img src="/logo.png" alt="Resqfy" className={c("brand-logo")} />
          </div>
        </section>

        <section className={c("form-panel")}>
          <div className={c("theme-switcher")}>
            <span className={c("switch-mode")}>
              {theme === "light" ? "LIGHT" : "DARK"}
            </span>
            <button
              type="button"
              className={c("theme-switch")}
              data-theme={theme}
              aria-label="Toggle theme"
              onClick={toggleTheme}
            >
              <span className={c("switch-icon switch-icon-left")}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <circle cx={12} cy={12} r={5} />
                  <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
                </svg>
              </span>
              <span className={c("switch-icon switch-icon-right")}>
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
                </svg>
              </span>
              <span className={c("switch-thumb")} />
            </button>
          </div>

          <div className={c("form-card")}>
            <h2 className={c("form-title")}>Log In</h2>
            <p className={c("form-subtitle")}>Enter your credentials to continue</p>

            <form className={c("auth-form")} onSubmit={handleSubmit}>
              {formError ? (
                <p className={c("form-alert form-alert-error")}>{formError}</p>
              ) : null}
              {formSuccess ? (
                <p className={c("form-alert form-alert-success")}>{formSuccess}</p>
              ) : null}

              <div className={c("field")}>
                <label htmlFor="login-identifier" className={c("sr-only")}>
                  Username or Email
                </label>
                <input
                  id="login-identifier"
                  type="text"
                  className={c("input")}
                  placeholder="ananya.rao or ananya.rao@gmail.com"
                  autoComplete="username"
                  value={identifier}
                  onChange={(event) => setIdentifier(event.target.value)}
                />
              </div>

              <div className={c("field")}>
                <label htmlFor="login-password" className={c("sr-only")}>
                  Password
                </label>
                <input
                  id="login-password"
                  type="password"
                  className={c("input")}
                  placeholder="Ananya@2026"
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
              </div>

              <div className={c("helper-row")}>
                <a href="#" className={c("helper-link")}>
                  Forgot password?
                </a>
              </div>

              <button
                type="submit"
                className={c("primary-btn")}
                disabled={isSubmitting}
              >
                {isSubmitting ? "Signing in..." : "Log In"}
              </button>
            </form>

            <div className={c("divider")}>
              <span>OR</span>
            </div>

            <button type="button" className={c("google-btn")}>
              <span className={c("google-icon")} aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none">
                  <path d="M23 12.2c0-.7-.1-1.4-.2-2.1H12v4h6.2c-.3 1.7-1.3 3.1-2.8 4l3.6 2.8c2.1-1.9 3.3-4.8 3.3-8.7z" fill="#4285F4" />
                  <path d="M12 23c3 0 5.5-1 7.3-2.7l-3.6-2.8c-1 .7-2.2 1.1-3.7 1.1-2.8 0-5.2-1.9-6-4.5L2.2 17c1.8 3.6 5.5 6 9.8 6z" fill="#34A853" />
                  <path d="M6 14.1c-.2-.7-.4-1.4-.4-2.1s.1-1.4.4-2.1L2.2 7C1.4 8.5 1 10.2 1 12s.4 3.5 1.2 5l3.8-2.9z" fill="#FBBC05" />
                  <path d="M12 5.4c1.6 0 3 .6 4.1 1.6l3.1-3.1C17.5 2.3 15 1.3 12 1.3c-4.3 0-8 2.4-9.8 5.7L6 9.9c.8-2.6 3.2-4.5 6-4.5z" fill="#EA4335" />
                </svg>
              </span>
              Sign in with Google
            </button>

            <p className={c("bottom-text")}>
              Don&apos;t have an account?{" "}
              <Link to="/signup" className={c("inline-link")}>
                Sign up
              </Link>
            </p>
            <p className={c("bottom-text")}>
              <Link to="/" className={c("inline-link")}>
                Back to Home
              </Link>
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
