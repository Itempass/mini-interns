const { z } = require('zod');

/**
 * Zod schema for server-side environment variables.
 * This will throw a build-time error if the environment variables
 * are invalid, ensuring type-safety.
 */
const serverEnvSchema = z.object({
  CONTAINERPORT_API: z.coerce.number().int().positive(),
});

const serverEnv = serverEnvSchema.parse(process.env);

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `http://127.0.0.1:${serverEnv.CONTAINERPORT_API}/:path*`,
      },
    ]
  },
  logging: {
    fetches: {
      fullUrl: true,
    },
  },
}
 
module.exports = nextConfig 