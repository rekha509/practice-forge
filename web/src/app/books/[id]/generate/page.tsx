import { GeneratorView } from "@/components/generator-view";

export default async function GeneratePage(props: PageProps<"/books/[id]/generate">) {
  const { id } = await props.params;
  return <GeneratorView bookId={id} />;
}
