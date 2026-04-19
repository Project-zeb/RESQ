import type { CapacitorConfig } from "@capacitor/cli";

const defaultServerUrl = process.env.CAP_SERVER_URL || "http://127.0.0.1:2000";

const config: CapacitorConfig = {
  appId: "com.resqfy.system",
  appName: "Resqfy System",
  webDir: "www",
  bundledWebRuntime: false,
  server: {
    url: defaultServerUrl,
    cleartext: true,
    androidScheme: "http"
  }
};

export default config;
