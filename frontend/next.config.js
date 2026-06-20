/** @type {import('next').NextConfig} */
const enableDevAuth = process.env.NEXT_PUBLIC_ENABLE_DEV_AUTH;
if (process.env.NEXT_PUBLIC_DEV_AUTH_EMAIL || process.env.NEXT_PUBLIC_DEV_AUTH_PASSWORD || (enableDevAuth && enableDevAuth !== "false")) {
  throw new Error(
    "BUILD BLOCKED: Development backdoor variables (NEXT_PUBLIC_DEV_AUTH_EMAIL, NEXT_PUBLIC_DEV_AUTH_PASSWORD, NEXT_PUBLIC_ENABLE_DEV_AUTH) are set. " +
    "These backdoors are forbidden in builds for security compliance."
  );
}


const nextConfig = {
  output: "standalone",
  skipTrailingSlashRedirect: true,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "X-Frame-Options",
            value: "DENY",
          },
          {
            key: "X-Content-Type-Options",
            value: "nosniff",
          },
          {
            key: "Strict-Transport-Security",
            value: "max-age=31536000; includeSubDomains",
          },
          {
            key: "Referrer-Policy",
            value: "strict-origin-when-cross-origin",
          },
          {
            key: "Content-Security-Policy",
            value: "default-src 'self'; script-src 'self' 'unsafe-eval' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; connect-src 'self' http://localhost:8000 https://api.openai.com;",
          },
        ],
      },
    ];
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
