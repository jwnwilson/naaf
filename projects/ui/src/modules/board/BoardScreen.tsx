import { useParams, useSearchParams } from "react-router-dom";
import { useProjects } from "../../lib/api/hooks/useProjects";
import { BoardView } from "./BoardView";
import { ListView } from "./ListView";

export function BoardScreen() {
  const { projectId: routeProjectId } = useParams<{ projectId?: string }>();
  const [params] = useSearchParams();
  const view = params.get("view") === "list" ? "list" : "board";

  const { data: projectsData, isLoading } = useProjects();
  const projectId = routeProjectId ?? params.get("project") ?? projectsData?.results[0]?.id;

  if (isLoading || !projectId) {
    return null;
  }

  return view === "list" ? (
    <ListView projectId={projectId} />
  ) : (
    <BoardView projectId={projectId} />
  );
}
