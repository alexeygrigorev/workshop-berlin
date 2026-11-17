import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";
import { auth } from "@/lib/api";

export const Route = createFileRoute("/_authenticated")({
  ssr: false,
  beforeLoad: async ({ location }) => {
    const user = await auth.getUser();
    if (!user) {
      localStorage.setItem("wswe_after_auth", location.href);
      throw redirect({ to: "/auth" });
    }
    return { user };
  },
  component: () => <Outlet />,
});
