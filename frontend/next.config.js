/** @type {import('next').NextConfig} */
const nextConfig = {
  devIndicators: false,
  // Docker/HF image builds a self-contained server (.next/standalone); local dev/start is unchanged.
  output: process.env.NEXT_OUTPUT === 'standalone' ? 'standalone' : undefined,
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/:path*',
      },
    ];
  },
};

module.exports = nextConfig;
