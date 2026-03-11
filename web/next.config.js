/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    const api = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
    return [{ source: '/api/:path*', destination: `${api}/:path*` }];
  },
  webpack: (config, { dev }) => {
    if (dev) {
      config.devtool = false;
    }
    return config;
  },
};

module.exports = nextConfig;
