import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL}/api/:path*`,
      },
      {
        source: "/files/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL}/files/:path*`,
      },
    ];
  },
};

export default nextConfig;
