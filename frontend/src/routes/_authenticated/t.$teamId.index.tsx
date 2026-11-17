import { createFileRoute } from "@tanstack/react-router";
import { useVote } from "./-vote-layouts/use-vote";
import { VoteStatus } from "./-vote-layouts/shared";
import { LayoutB } from "./-vote-layouts/layout-b";

export const Route = createFileRoute("/_authenticated/t/$teamId/")({
  head: () => ({ meta: [{ title: "Today's vote — Where Should We Eat?" }] }),
  component: TodayPage,
});

function TodayPage() {
  const { teamId } = Route.useParams();
  const v = useVote(teamId);
  return v.status === "ready" ? <LayoutB v={v} /> : <VoteStatus v={v} teamId={teamId} />;
}
