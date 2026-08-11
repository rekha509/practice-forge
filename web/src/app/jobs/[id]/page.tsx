import { JobProgressView } from "@/components/job-progress-view";

export default async function JobPage(props: PageProps<"/jobs/[id]">) {
  const { id } = await props.params;
  return <JobProgressView jobId={id} />;
}
