import { ProblemSetView } from "@/components/problem-set-view";

export default async function ProblemSetPage(props: PageProps<"/problem-sets/[id]">) {
  const { id } = await props.params;
  return <ProblemSetView problemSetId={id} />;
}
